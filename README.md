# css

A local MCP server that lets Claude run shell commands on your computer. macOS is supported using the setup and launch scripts below; the Python server also remains usable on Windows.

> **Security:** This server can execute shell commands. It binds to `127.0.0.1` and requires its generated token. Keep it local, use a dedicated projects directory for `CLAUDE_SHELL_ROOTS`, and do not expose it to the internet or an untrusted network.

## macOS setup

Requirements: macOS and Python 3.10 or later. Install Python from [python.org](https://www.python.org/downloads/macos/) or with Homebrew (`brew install python`), then from the repository directory run:

```bash
bash setup.sh
```

The setup script creates a virtual environment, installs the Python dependencies, and creates `config.env`. The default allowed deletion root and working directory are `~/projects`; you can choose a different directory when prompted. Deletions require a confirmation dialog and are blocked at the configured root or above the configured minimum depth.

Start the server with:

```bash
bash start.sh
```

The generated authentication token and local MCP URL are printed at startup. Configure your MCP client to use that URL. Keep the terminal running while using the server. Stop it with `Ctrl-C`.

If Python was installed without Tk support, setup warns that destructive commands will be denied because the confirmation dialog cannot open. Install a Python build with Tk support to enable those dialogs.

## Configuration

`config.env` is sourced by `start.sh` and is created locally by setup. It is not intended to be committed. You can edit it to set:

- `CLAUDE_SHELL_CWD`: default working directory.
- `CLAUDE_SHELL_ROOTS`: path(s) where deletion may be considered, separated by `:` on macOS.
- `CLAUDE_SHELL_MIN_DEPTH`: minimum depth below an allowed root for deletion (default `2`).
- `PORT`: local HTTP port (default `8765`).
- `CLAUDE_SHELL_TOKEN`: optional fixed authentication token; otherwise a new token is generated at launch.

## Windows

The existing `setup.ps1` provides the Windows setup flow. The server requires Python 3.10 or later.
