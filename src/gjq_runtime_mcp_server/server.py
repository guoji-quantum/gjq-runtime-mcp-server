"""FastMCP server exposing the GuoJi / CETC-ICQ Quantum Cloud Platform.

Tools wrap the synchronous gjq-client SDK via ``asyncio.to_thread`` so the MCP
event loop is never blocked. Every tool returns a dict containing a ``status``
field ("success" or "error").
"""

from __future__ import annotations

import asyncio
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

from . import circuits, runtime

load_dotenv()

mcp = FastMCP("gjq-runtime")
_TERMINAL_TASK_STATUSES = {"DONE", "ERROR", "CANCELLED"}


async def _run(func, /, *args, **kwargs) -> Any:
    return await asyncio.to_thread(func, *args, **kwargs)


def _ok(**data: Any) -> dict[str, Any]:
    return {"status": "success", **data}


def _err(exc: Exception) -> dict[str, Any]:
    return {"status": "error", "error": str(exc), "error_type": type(exc).__name__}


# ==========================================================================
# Account management
# ==========================================================================


@mcp.tool
async def setup_gjq_account_tool(
    api_key: str,
    channel: str = "gjq_cloud",
    base_url: str | None = None,
    backend_url: str | None = None,
) -> dict[str, Any]:
    """Configure and cache the GuoJi Quantum cloud account credentials.

    The api_key is persisted to ~/.gjq_client/gjq_client_account.json for reuse.

    SECURITY: the api_key is passed as a tool argument, so it can end up in the
    LLM context and in client/transport logs. Prefer setting the GJQ_API_KEY
    environment variable; use this tool only in a trusted local setup.
    """
    try:
        await _run(runtime.configure_account, api_key, channel, base_url, backend_url)
        return _ok(account=await _run(runtime.active_account_info))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
async def active_account_info_tool() -> dict[str, Any]:
    """Get the currently configured account info (api_key masked)."""
    try:
        return _ok(account=await _run(runtime.active_account_info))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ==========================================================================
# Device management
# ==========================================================================


@mcp.tool
async def list_backends_tool() -> dict[str, Any]:
    """List all available quantum backends (devices/simulators)."""
    try:
        backends = await _run(runtime.list_backends)
        return _ok(total=len(backends), backends=backends)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
async def get_backend_configuration_tool(backend_name: str) -> dict[str, Any]:
    """Get the static configuration of a backend (basis gates, n_qubits, etc.)."""
    try:
        config = await _run(runtime.backend_configuration, backend_name)
        return _ok(configuration=config)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
async def get_backend_properties_tool(backend_name: str) -> dict[str, Any]:
    """Get calibration properties of a backend (T1/T2, gate errors). May be null."""
    try:
        props = await _run(runtime.backend_properties, backend_name)
        return _ok(properties=props)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
async def least_busy_tool() -> dict[str, Any]:
    """Return the name of the least busy available backend."""
    try:
        name = await _run(runtime.least_busy_backend_name)
        return _ok(backend_name=name)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ==========================================================================
# Compute tasks
# ==========================================================================


@mcp.tool
async def sample_tool(
    qasm: str,
    backend_name: str,
    shots: int = 1024,
    optimization_level: int = 1,
    transpile: bool = True,
    amplitude_index: list[int] | None = None,
) -> dict[str, Any]:
    """Submit a sampling task. Provide the circuit as an OpenQASM 2.0 string
    (OpenQASM 3 also works if the optional ``qiskit_qasm3_import`` is installed).

    Returns a task_id; poll get_task_status_tool then get_task_result_tool.
    SAS-CPU simulator requires amplitude_index.
    """
    try:
        task_id = await _run(
            runtime.submit_sample,
            backend_name,
            qasm,
            shots,
            optimization_level,
            transpile,
            amplitude_index,
        )
        return _ok(task_id=task_id, submissions_used=runtime.submission_count())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
async def estimate_tool(
    qasm: str,
    backend_name: str,
    observable: list,
    shots: int = 1024,
    optimization_level: int = 1,
    transpile: bool = True,
    amplitude_index: list[int] | None = None,
) -> dict[str, Any]:
    """Submit an expectation-estimation task.

    observable is a list like [["ZZ", 1.0], ["XX", 0.5]] (Pauli string + coeff).
    Returns a task_id; fetch results with get_task_result_tool(task_id, observable).
    """
    try:
        task_id = await _run(
            runtime.submit_estimate,
            backend_name,
            qasm,
            observable,
            shots,
            optimization_level,
            transpile,
            amplitude_index,
        )
        return _ok(task_id=task_id, submissions_used=runtime.submission_count())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ==========================================================================
# Task management (non-blocking)
# ==========================================================================


@mcp.tool
async def get_task_status_tool(task_id: str) -> dict[str, Any]:
    """Get task status: INITIALIZING / QUEUED / RUNNING / DONE / ERROR / CANCELLED."""
    try:
        state = await _run(runtime.task_status, task_id)
        return _ok(task_id=task_id, task_status=state)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
async def get_task_result_tool(
    task_id: str, observable: list | None = None
) -> dict[str, Any]:
    """Get the result of a task.

    While the task is still running the result is empty and ``pending`` is true;
    check ``task_status`` to see the current state. Pass observable (same format
    as estimate_tool) to compute expectation values.
    """
    try:
        result = await _run(runtime.task_result, task_id, observable)
        status = await _run(runtime.task_status, task_id)
        pending = status not in _TERMINAL_TASK_STATUSES
        return _ok(task_id=task_id, task_status=status, pending=pending, result=result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
async def get_task_log_tool(task_id: str) -> dict[str, Any]:
    """Get the execution log of a task."""
    try:
        log = await _run(runtime.task_log, task_id)
        return _ok(task_id=task_id, log=log)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
async def get_task_detail_tool(task_id: str) -> dict[str, Any]:
    """Get task details (backend, shots, submit time)."""
    try:
        detail = await _run(runtime.task_detail, task_id)
        return _ok(task_id=task_id, detail=detail)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
async def list_my_tasks_tool() -> dict[str, Any]:
    """List the current user's tasks."""
    try:
        tasks = await _run(runtime.list_tasks)
        return _ok(total=len(tasks), tasks=tasks)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ==========================================================================
# Resources
# ==========================================================================


@mcp.resource("gjq://status")
def service_status() -> dict[str, Any]:
    """Service status and active anti-abuse limits."""
    return {
        "service": "gjq-runtime-mcp-server",
        "account": runtime.active_account_info(),
        "max_shots": runtime.max_shots(),
        "max_submissions_per_session": runtime.max_submissions(),
        "submissions_used": runtime.submission_count(),
    }


@mcp.resource("circuits://{name}")
def example_circuit(name: str) -> str:
    """Return an example circuit as an OpenQASM string."""
    qasm = circuits.EXAMPLES.get(name)
    if qasm is None:
        available = ", ".join(sorted(circuits.EXAMPLES))
        raise ValueError(f"Unknown circuit '{name}'. Available: {available}")
    return qasm


def run() -> None:
    mcp.run()
