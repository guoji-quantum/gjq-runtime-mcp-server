# GJQ Runtime MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that lets
AI assistants interact with the **GuoJi / CETC-ICQ Quantum Cloud Platform** through
the [`gjq-client`](https://pypi.org/project/gjq-client/) Qiskit 2.0 SDK.

[中文文档](README_zh.md)

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

## Installation

```bash
git clone <this-repo>
cd gjq-runtime-mcp-server

python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/macOS:  source .venv/bin/activate

pip install -e .
```

## Quick start

```bash
cp .env.example .env
# Edit .env and set GJQ_API_KEY=your_api_key_here

python -m gjq_runtime_mcp_server
```

Get your API key from <https://www.tiangongqs.com/cloud>.

## MCP tools

### Account
| Tool | Description |
|------|-------------|
| `setup_gjq_account_tool` | Configure and cache cloud account credentials |
| `active_account_info_tool` | Show the active account (api_key masked) |

### Device
| Tool | Description |
|------|-------------|
| `list_backends_tool` | List all available backends |
| `get_backend_configuration_tool` | Static config of a backend |
| `get_backend_properties_tool` | Calibration data (T1/T2, gate errors) |
| `least_busy_tool` | Name of the least busy backend |

### Compute
| Tool | Description |
|------|-------------|
| `sample_tool` | Submit a sampling task (OpenQASM circuit) |
| `estimate_tool` | Submit an expectation-estimation task |

### Task management
| Tool | Description |
|------|-------------|
| `get_task_status_tool` | Task status (INITIALIZING/QUEUED/RUNNING/DONE/ERROR) |
| `get_task_result_tool` | Result (counts, or expectation values with an observable) |
| `get_task_log_tool` | Execution log |
| `get_task_detail_tool` | Backend / shots / submit time |
| `list_my_tasks_tool` | List the user's tasks |

## MCP resources

| URI | Description |
|-----|-------------|
| `gjq://status` | Service status and active limits |
| `circuits://bell-state` | Bell state example (OpenQASM) |
| `circuits://ghz-state` | GHZ state example |
| `circuits://superposition` | Superposition example |
| `circuits://random` | Random-bit circuit example |

## Configure in MCP clients (Cursor)

Create `.cursor/mcp.json` in the project root (Windows template):

```json
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
```

Verify in Cursor:
1. Restart Cursor.
2. Go to `Cursor Settings → Tools & MCPs → Installed MCP Servers`.
3. Confirm `gjq-runtime` is listed, turn on the switch, and check that a green dot is shown.

The JSON above also applies to JSON-based clients such as Cursor and Claude Desktop.

| Client | Config file |
|--------|-------------|
| Cursor | `.cursor/mcp.json` (project root) |
| Claude Desktop | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Codex CLI | `~/.codex/config.toml` (TOML, see below) |

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
`~/.cursor/skills/` (personal):

```bash
cp -r skills/gjq-quantum-runtime ~/.cursor/skills/
```

## Example circuit (sampling)

```python
# sample_tool input
qasm = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
h q[0];
cx q[0],q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];"""
# -> {"status": "success", "task_id": "..."}
# then poll get_task_status_tool, then get_task_result_tool
```

> OpenQASM 2.0 works out of the box. To submit OpenQASM 3 circuits, install the
> optional parser: `pip install qiskit_qasm3_import`.

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
