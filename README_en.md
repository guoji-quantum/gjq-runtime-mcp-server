# GJQ Runtime MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that lets
AI assistants interact with the **GuoJi / CETC-ICQ Quantum Cloud Platform** through
the [`gjq-client`](https://pypi.org/project/gjq-client/) Qiskit 2.0 SDK.

[中文文档](README.md)

<img src="docs/brief.png" alt="brief" width="800">

## Features

- **Account management**: configure and inspect cloud credentials
- **Device management**: list backends, query configuration / calibration, find the least busy device
- **Compute tasks**: submit sampling and expectation-estimation jobs from OpenQASM
- **Task management**: poll status, fetch results / logs / details, list your tasks
- **Example circuits**: Bell / GHZ / superposition / random as MCP resources

### Feature Screenshots

<img src="docs/sample1.png" alt="sample1" width="320">
<img src="docs/sample2.png" alt="sample2" width="320">
<img src="docs/sample3.png" alt="sample3" width="320">

## Install and start (Cursor example)

1. Clone the repo and create a virtual environment

```bash
git clone <this-repo>
cd gjq-runtime-mcp-server
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -e .
```

2. Rename `.env.example` to `.env`, then set `GJQ_API_KEY=your_api_key_here`. (Get your API key from <https://www.tiangongqs.com/cloud>)

3. Start the MCP server locally (quick runtime check)

```bash
python -m gjq_runtime_mcp_server
```

4. Create `.cursor/mcp.json` in the project root

```json
# Windows (remove this line)
{
  "mcpServers": {
    "gjq-runtime": {
      "command": ".venv\\Scripts\\python.exe",
      "args": ["-m", "gjq_runtime_mcp_server"],
      "cwd": "/path/to/gjq-runtime-mcp-server",
      "env": { "GJQ_API_KEY": "your_api_key_here" }
    }
  }
}

# Linux/macOS (remove this line)
{
  "mcpServers": {
    "gjq-runtime": {
      "command": ".venv/bin/python",
      "args": ["-m", "gjq_runtime_mcp_server"],
      "cwd": "/path/to/gjq-runtime-mcp-server",
      "env": { "GJQ_API_KEY": "your_api_key_here" }
    }
  }
}
```

5. Verify in Cursor

- Restart Cursor.
- Go to `Cursor Settings → Tools & MCPs → Installed MCP Servers`.
- Confirm `gjq-runtime` is listed, turn on the switch, and check that a green dot is shown.

## MCP tools

- Account: `setup_gjq_account_tool`, `active_account_info_tool`
- Device: `list_backends_tool`, `get_backend_configuration_tool`, `get_backend_properties_tool`, `least_busy_tool`
- Compute: `sample_tool`, `estimate_tool`
- Task: `get_task_status_tool`, `get_task_result_tool`, `get_task_log_tool`, `get_task_detail_tool`, `list_my_tasks_tool`

All tools return `{"status": "success" | "error", ...}`.

> OpenQASM 2.0 works out of the box. To submit OpenQASM 3 circuits, install:
> `pip install qiskit_qasm3_import`.

## MCP resources

`gjq://status`, `circuits://bell-state`, `circuits://ghz-state`, `circuits://superposition`, `circuits://random`

## Other MCP client configuration

The JSON above also applies to JSON-based clients such as Cursor and Claude Desktop.

| Client | Config file |
|--------|-------------|
| Cursor | `.cursor/mcp.json` (project root) |
| Claude Desktop | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Codex | `~/.codex/config.toml` (TOML, see below) |

Codex CLI uses TOML instead of JSON. Add the following to `~/.codex/config.toml`
(the top-level table must be `mcp_servers`):

```toml
[mcp_servers.gjq-runtime]
command = "/path/to/gjq-runtime-mcp-server/.venv/bin/python"
args = ["-m", "gjq_runtime_mcp_server"]
cwd = "/path/to/gjq-runtime-mcp-server"

[mcp_servers.gjq-runtime.env]
GJQ_API_KEY = "your_api_key_here"
```

## Agent skill

A companion skill lives in [`skills/gjq-quantum-runtime/`](skills/gjq-quantum-runtime/SKILL.md).
To use it in Cursor, copy that folder into `.cursor/skills/` (project) or
`~/.cursor/skills/` (personal).

## Security notes

- The API key is stored **in plaintext** at `~/.gjq_client/gjq_client_account.json`
  and in your MCP client config `env`. Treat it as a secret; never commit `.env`.

## Development

```bash
pip install -e ".[test]"
pytest
```

## License

Apache License 2.0
