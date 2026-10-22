# css mcp for personal use

import glob
import os
import re
import secrets
import shlex
import subprocess
import sys
import time

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

PORT = int(os.environ.get("PORT", "8765"))
TOKEN = os.environ.get("CLAUDE_SHELL_TOKEN") or secrets.token_urlsafe(32)
WORKDIR = os.path.realpath(os.path.expanduser(os.environ.get("CLAUDE_SHELL_CWD", os.getcwd())))
ROOTS = [
    os.path.realpath(os.path.expanduser(p))
    for p in os.environ.get("CLAUDE_SHELL_ROOTS", WORKDIR).split(os.pathsep)
    if p.strip()
]
MIN_DEPTH = int(os.environ.get("CLAUDE_SHELL_MIN_DEPTH", "2"))
CONFIRM_TIMEOUT = 60
MAX_OUT = 20_000
LOG = os.environ.get("CLAUDE_SHELL_LOG", "claude_shell.log")

mcp = FastMCP(
    "local-shell",
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _log(line: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} {line}\n")



DELETE_CMDS = {"rm", "rmdir", "unlink", "shred", "del", "erase", "rd", "remove-item", "ri"}
WRAPPERS = {"sudo", "command", "env", "nohup", "time", "nice", "builtin", "doas"}


HARD_BLOCK = re.compile(
    r"(\bmkfs\b|\bdd\b[^;&|]*\bof=/dev/|:\(\)\s*\{|\bformat\s+[a-z]:|>\s*/dev/sd[a-z])", re.I
)
AMBIGUOUS = re.compile(
    r"(\brmtree\b|os\.(remove|unlink|rmdir)\b|\bshutil\.|\s-delete\b|--delete\b|--remove-source-files"
    r"|git\s+clean|git\s+reset\s+--hard|git\s+rm\b|\btruncate\b)",
    re.I,
)


def _tokens(command: str):
    command = command.replace("\n", " ; ")
    lex = shlex.shlex(command, posix=(os.name != "nt"), punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


def _segments(tokens):
    seg = []
    for t in tokens:
        if t and all(c in ";&|()" for c in t):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(t)
    if seg:
        yield seg


def _path_status(path: str):
    for root in ROOTS:
        if path == root:
            return f"{path} is a protected root"
        if path.startswith(root + os.sep):
            depth = len(os.path.relpath(path, root).split(os.sep))
            if depth >= MIN_DEPTH:
                return "ok"
            return f"{path} is an important folder (depth {depth}, minimum allowed is {MIN_DEPTH})"
    return f"{path} is outside the permitted folders {ROOTS}"


def _describe(path: str) -> str:
    if os.path.isdir(path):
        n = 0
        for _, dirs, files in os.walk(path):
            n += len(dirs) + len(files)
            if n > 1000:
                return f"{path}  (folder)"
        return f"{path}  (folder, {n} files)"
    if os.path.exists(path):
        return f"{path}  (file)"
    return f"{path}  (does not exist)"


def review(command: str, cwd: str):
    """Return ('allow'|'block'|'confirm', message_or_list)."""
    if HARD_BLOCK.search(command):
        return "block", "Comando blocked"
    try:
        tokens = _tokens(command)
    except ValueError as e:
        return "block", f"Could not parse the command ({e}). Simplify it."

    to_confirm: list[str] = []
    ambiguous = bool(AMBIGUOUS.search(command))
    cur = cwd 

    for seg in _segments(tokens):
        seg = [t for t in seg if t not in ("<", ">", ">>", "2>", "2>&1")]
        while seg and (re.match(r"^\w+=", seg[0]) or seg[0] in WRAPPERS):
            seg = seg[1:]
        if not seg:
            continue
        name = os.path.basename(seg[0]).lower()

        if name in ("cd", "pushd") and len(seg) >= 2:
            arg = seg[1]
            if "$" in arg or "`" in arg:
                cur = None
            else:
                base = cur or WORKDIR
                cur = os.path.realpath(os.path.join(base, os.path.expanduser(arg)))
            continue

        if name in DELETE_CMDS:
            targets, after_dd = [], False
            for t in seg[1:]:
                if t == "--" and not after_dd:
                    after_dd = True
                elif after_dd or not (t.startswith("-") or (os.name == "nt" and t.startswith("/") and len(t) <= 3)):
                    targets.append(t)
            for t in targets:
                if "$" in t or "`" in t:
                    return "block", "Deletion using variables/subshells is not allowed; use literal paths."
                t = os.path.expanduser(t)
                if cur is None and not os.path.isabs(t):
                    return "block", "Cannot determine the current directory; use absolute paths for deletion."
                full = t if os.path.isabs(t) else os.path.join(cur, t)
                matches = glob.glob(full) or [full]
                for m in matches:
                    rp = os.path.realpath(m)
                    status = _path_status(rp)
                    if status != "ok":
                        return "block", f"Deletion blocked: {status}."
                    to_confirm.append(_describe(rp))
        elif any(os.path.basename(t).lower() in DELETE_CMDS for t in seg[1:]):
            ambiguous = True 

    if to_confirm:
        return "confirm", to_confirm
    if ambiguous:
        return "confirm", ["(Destructive deletion/modification that cannot be analyzed; review the full command)"]
    return "allow", ""


POPUP = r"""
import sys, tkinter as tk
from tkinter import messagebox
r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
ok = messagebox.askyesno("Claude Shell - confirm delete", sys.argv[1], icon="warning", default="no", parent=r)
sys.exit(0 if ok else 1)
"""


def ask_user(items: list[str], command: str) -> bool:
    msg = "Claude wants to delete:\n\n" + "\n".join(f" • {i}" for i in items)
    msg += f"\n\nCommand:\n{command}\n\nAllow?"
    try:
        p = subprocess.run([sys.executable, "-c", POPUP, msg], timeout=CONFIRM_TIMEOUT)
        return p.returncode == 0 
    except Exception:
        return False

@mcp.tool()
def run_command(command: str, cwd: str | None = None, timeout: int = 30) -> str:
    run_cwd = os.path.realpath(os.path.expanduser(cwd)) if cwd else WORKDIR
    verdict, info = review(command, run_cwd)
    _log(f"{verdict.upper()} cwd={run_cwd} cmd={command!r}")

    if verdict == "block":
        return f"[BLOQUEADO] {info}"
    if verdict == "confirm":
        if not ask_user(info, command):
            _log("  -> user DENIED")
            return "[DENIED] The user rejected (or did not respond to) the deletion confirmation."
        _log("  -> user ALLOWED")

    try:
        p = subprocess.run(
            command, shell=True, cwd=run_cwd, capture_output=True, text=True, timeout=min(timeout, 120)
        )
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s"
    out = f"[exit {p.returncode}]\n--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}"
    return out[:MAX_OUT] + ("\n...[truncated]" if len(out) > MAX_OUT else "")

class TokenAuth:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode()
        ok = auth.startswith("Bearer ") and secrets.compare_digest(auth[7:], TOKEN)

        path = scope["path"]
        parts = path.split("/", 2) 
        if not ok and len(parts) >= 2 and secrets.compare_digest(parts[1], TOKEN):
            ok = True
            new_path = "/" + (parts[2] if len(parts) > 2 else "")
            scope = dict(scope, path=new_path, raw_path=new_path.encode())

        if not ok:
            _log(f"DENIED {scope.get('client')} {path[:40]}")
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"Unauthorized"})
            return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    print(f"\nToken: {TOKEN}")
    print(f"Deletion roots: {ROOTS} (minimum depth {MIN_DEPTH})")
    print(f"Local:  http://localhost:{PORT}/{TOKEN}/mcp")
    print(f"Tunnel: cloudflared tunnel --url http://localhost:{PORT}\n")
    uvicorn.run(TokenAuth(mcp.streamable_http_app()), host="127.0.0.1", port=PORT)
