# Proposal: public accessors on gjq-client (GJQRuntimeService / RuntimeJob)

Audience: gjq-client SDK team
Requested by: gjq-runtime-mcp-server
Status: draft for review

## Summary

`gjq-runtime-mcp-server` currently reaches into SDK internals because
`GJQRuntimeService` and `RuntimeJob` expose no public equivalents for a few
needed operations. We ask the SDK to publish stable, versioned accessors so the
MCP server (and other consumers) can drop all `_`-prefixed access.

Today's internal touch points (all isolated in `runtime.py`):

```python
get_service()._client.task_log(task_id)
get_service()._client.task_detail(task_id)
get_service()._client.backend_configuration(name)
get_service()._client.backend_properties(name)
job._job_id   # annotated list[str], currently returns a single str
```

Risk: these break silently at import and only fail at runtime if the SDK renames
`_client` / changes signatures. There is no type guarantee on `_job_id`.

## Design choice: facade methods, not exposing `_client`

We specifically ask for **delegating methods on `GJQRuntimeService`**, not for
making `_client` (the `RuntimeClient`) public. Rationale:

- Exposing `_client` turns the entire `RuntimeClient` surface (submit_task,
  unwrap helpers, sessions, simulator builders) into a public contract the SDK
  must keep stable.
- A small facade keeps the public surface curated, lets the SDK refactor
  internals freely, and lets the SDK own/normalize return types.
- It avoids a confusing dual API (`service.list_backends()` vs
  `service.client.list_backends()`).

## Request 1: public methods on `GJQRuntimeService`

Add four methods that delegate to the internal client, returning raw dicts
consistent with the existing `task_status` / `task_result`:

```python
def task_log(self, task_id: str) -> dict: ...           # {"instanceId", "log"}
def task_detail(self, task_id: str) -> dict: ...         # {"backend_name", "shots", "instanceId", "submit_time"}
def backend_configuration(self, backend_name: str) -> dict: ...  # basis_gates, n_qubits, coupling_map, ...
def backend_properties(self, backend_name: str) -> dict | None: ...  # qubits/gates calibration, may be None
```

Notes:
- Please document and type the return shapes so they form a stable contract.
- Keep error behaviour aligned with existing methods (e.g. `BackendNotFoundError`,
  `JobNotFoundError`).

## Request 2: public job id accessor on `RuntimeJob` (batch-aware)

Batch submission is planned, so a plain `job_id: list[str]` rename would push
batch complexity onto the common single-task path. We propose two properties:

```python
@property
def job_ids(self) -> list[str]:
    """All task ids for this job (always a list; length 1 for single submit)."""

@property
def job_id(self) -> str:
    """Convenience accessor for the single-task case.
    Raises if the job represents multiple tasks (use job_ids instead).
    """
```

This keeps `job.job_id -> str` ergonomic today and makes `job.job_ids` the
forward-compatible accessor once batch lands.

## Versioning / rollout

- Ship in a minor release (e.g. 0.2.0). Both requests are purely additive and
  backward compatible, except any intentional change to the `_job_id` contract,
  which should be settled together with the batch design.
- On the consumer side, the MCP server pins `gjq-client>=0.1.2,<0.2` until this
  lands; after release we bump the pin and replace the internal access in
  `runtime.py` (single file, covered by tests).

## Acceptance criteria

- `GJQRuntimeService` exposes `task_log`, `task_detail`, `backend_configuration`,
  `backend_properties` with documented return types.
- `RuntimeJob` exposes `job_id` (str) and `job_ids` (list[str]).
- MCP `runtime.py` contains no `service._client` / `job._job_id` access and the
  test suite (including the FAS-CPU Bell-state integration) passes.
