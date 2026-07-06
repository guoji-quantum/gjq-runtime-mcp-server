---
name: gjq-quantum-runtime
description: Run quantum circuits on the GuoJi / CETC-ICQ Quantum Cloud Platform through the gjq-runtime MCP server. Use when the user wants to list quantum backends, submit sampling or expectation-estimation jobs, transpile circuits, or poll quantum task status and results via the gjq MCP tools.
---

# GJQ Quantum Runtime

Drive the GuoJi / CETC-ICQ Quantum Cloud Platform via the `gjq-runtime` MCP server. The server wraps the `gjq-client` Qiskit SDK and exposes account, device, compute, and task-management tools.

## When to use

- Listing available quantum backends / picking the least busy one.
- Submitting a circuit for sampling (measurement counts) or estimation (expectation value of an observable).
- Checking task status and retrieving results.

## Tool map

| Goal | Tool |
|------|------|
| Configure account | `setup_gjq_account_tool(api_key, channel="gjq_cloud")` |
| Check account | `active_account_info_tool()` |
| List devices | `list_backends_tool()` |
| Least busy device | `least_busy_tool()` |
| Device config / calibration | `get_backend_configuration_tool(name)` / `get_backend_properties_tool(name)` |
| Submit sampling | `sample_tool(qasm, backend_name, shots=1024)` |
| Submit estimation | `estimate_tool(qasm, backend_name, observable, shots=1024)` |
| Poll status | `get_task_status_tool(task_id)` |
| Get result | `get_task_result_tool(task_id, observable=None)` |
| Log / detail / list | `get_task_log_tool` / `get_task_detail_tool` / `list_my_tasks_tool` |

Every tool returns `{"status": "success" | "error", ...}`. On error, read `error` / `error_type`.

## Workflow

```
- [ ] 1. Ensure account configured (active_account_info_tool; setup if needed)
- [ ] 2. Pick a backend (list_backends_tool or least_busy_tool)
- [ ] 3. Provide the circuit as an OpenQASM 2.0 string (must include measurements for sampling)
- [ ] 4. Submit (sample_tool / estimate_tool) -> capture task_id
- [ ] 5. Poll get_task_status_tool until "DONE"
- [ ] 6. Fetch get_task_result_tool(task_id)
```

Status values: `INITIALIZING`, `QUEUED`, `RUNNING`, `DONE`, `ERROR`, `CANCELLED`.

## Conventions

- **Circuit input**: OpenQASM 2.0 string (OpenQASM 3 works only if `qiskit_qasm3_import` is installed). Include `measure` for sampling. `transpile=True` (default) transpiles for the target backend; set `optimization_level` 0-3.
- **Observable** (estimation): list of `[pauli_string, coefficient]`, e.g. `[["ZZ", 1.0], ["XX", 0.5]]`. Pass the same observable to `get_task_result_tool` to read expectation values (`result.evs`).
- **Simulators**: `FAS-CPU` (full-state) and `SAS-CPU`. `SAS-CPU` requires `amplitude_index` (e.g. `[0]`).
- **Polling is explicit**: result/status tools never block. Poll at a reasonable cadence (a few seconds), do not tight-loop.

## Safety limits

The server enforces guards (configurable via env): `GJQ_MAX_SHOTS` (default 100000) and `GJQ_MAX_SUBMISSIONS_PER_SESSION` (default 20). Do not loop-submit jobs; reuse a `task_id` for status/result instead of resubmitting.

## Example: Bell state on FAS-CPU

1. `list_backends_tool()` -> confirm `FAS-CPU` is available.
2. `sample_tool(qasm=..., backend_name="FAS-CPU", shots=1024)` with:

```
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
h q[0];
cx q[0],q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
```

3. Capture `task_id` from the response.
4. `get_task_status_tool(task_id)` until `"DONE"`.
5. `get_task_result_tool(task_id)` -> `result.counts` ~ `{"00": ~512, "11": ~512}`.

Ready-made circuits are available as MCP resources: `circuits://bell-state`, `circuits://ghz-state`, `circuits://superposition`, `circuits://random`.
