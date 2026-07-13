"""Thin wrapper layer over the gjq-client SDK for the MCP server.

Responsibilities:
- Lazily build and cache a single ``GJQRuntimeService`` from env / explicit api_key.
- Convert OpenQASM strings into Qiskit ``QuantumCircuit`` objects.
- Convert observable lists into ``SparsePauliOp``.
- Enforce conservative anti-abuse guards (shots cap, per-session submit cap).

All functions here are synchronous; the MCP layer wraps them with
``asyncio.to_thread`` so the event loop is never blocked.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from gjq_client import (
    GJQRuntimeService,
    Sampler,
    Estimator,
    generate_preset_pass_manager,
)
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp

# Account config file written by gjq-client when an api_key is supplied.
ACCOUNT_CONFIG_FILE = Path.home() / ".gjq_client" / "gjq_client_account.json"

_service: GJQRuntimeService | None = None
_service_lock = threading.Lock()
_sdk_account_temp_dir = None

# Per-process submission counter (resets when the server restarts).
_submission_count = 0
_submission_lock = threading.Lock()


class GuardError(Exception):
    """Raised when an anti-abuse guard rejects an operation."""


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def max_shots() -> int:
    return _env_int("GJQ_MAX_SHOTS", 100000)


def max_submissions() -> int:
    return _env_int("GJQ_MAX_SUBMISSIONS_PER_SESSION", 20)


def _use_ephemeral_sdk_account_config() -> None:
    """Keep env-provided credentials from requiring/writing the user's HOME."""
    global _sdk_account_temp_dir
    if _sdk_account_temp_dir is None:
        _sdk_account_temp_dir = tempfile.TemporaryDirectory(prefix="gjq-runtime-")
    config_file = Path(_sdk_account_temp_dir.name) / "gjq_client_account.json"

    import gjq_client.gjq_runtime.gjq_runtime_service as sdk_runtime_service

    sdk_runtime_service._DEFAULT_ACCOUNT_CONFIG_JSON_FILE = str(config_file)


def configure_account(
    api_key: str,
    channel: str = "gjq_cloud",
    base_url: str | None = None,
    backend_url: str | None = None,
) -> GJQRuntimeService:
    """Create (and cache) a service with the given credentials.

    Passing an api_key causes gjq-client to persist the account config to
    ``~/.gjq_client/gjq_client_account.json`` for subsequent runs.
    """
    global _service
    with _service_lock:
        _service = GJQRuntimeService(
            channel=channel,
            api_key=api_key,
            base_url=base_url or None,
            backend_url=backend_url or None,
        )
    return _service


def get_service() -> GJQRuntimeService:
    """Return the cached service, building one from env / cached config if needed.

    Resolution order:
        1. Already-cached service instance.
        2. ``GJQ_API_KEY`` (+ optional channel/url overrides) from env.
        3. Cached config file at ``~/.gjq_client/gjq_client_account.json``.
    """
    global _service
    if _service is not None:
        return _service

    with _service_lock:
        if _service is not None:
            return _service

        api_key = os.environ.get("GJQ_API_KEY")
        channel = os.environ.get("GJQ_CHANNEL") or "gjq_cloud"
        base_url = os.environ.get("GJQ_BASE_URL") or None
        backend_url = os.environ.get("GJQ_BACKEND_URL") or None

        if api_key:
            _use_ephemeral_sdk_account_config()
            _service = GJQRuntimeService(
                channel=channel,
                api_key=api_key,
                base_url=base_url,
                backend_url=backend_url,
            )
        else:
            # No env key: rely on cached config file (raises FileNotFoundError
            # inside gjq-client if absent, which we surface as a clear error).
            if not ACCOUNT_CONFIG_FILE.exists():
                raise GuardError(
                    "No GJQ account configured. Set GJQ_API_KEY or call "
                    "setup_gjq_account_tool first."
                )
            _service = GJQRuntimeService(channel=channel)
        return _service


def _mask_api_key(api_key: str) -> str:
    return (api_key[:4] + "***" + api_key[-2:]) if len(api_key) > 6 else "***"


def active_account_info() -> dict[str, Any]:
    """Return the active account info with the api_key masked."""
    api_key = os.environ.get("GJQ_API_KEY")
    if api_key:
        return {
            "configured": True,
            "source": "env",
            "channel": os.environ.get("GJQ_CHANNEL") or "gjq_cloud",
            "api_key": _mask_api_key(api_key),
            "base_url": os.environ.get("GJQ_BASE_URL") or None,
            "backend_url": os.environ.get("GJQ_BACKEND_URL") or None,
        }

    if not ACCOUNT_CONFIG_FILE.exists():
        return {"configured": False}
    try:
        data = json.loads(ACCOUNT_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "configured": False,
            "error": f"Failed to read GJQ account config: {exc}",
        }
    api_key = data.get("api_key") or ""
    return {
        "configured": True,
        "source": "file",
        "channel": data.get("channel"),
        "api_key": _mask_api_key(api_key),
        "base_url": data.get("base_url"),
        "backend_url": data.get("backend_url"),
    }


def qasm_to_circuit(qasm: str) -> QuantumCircuit:
    """Parse an OpenQASM 3 (preferred) or OpenQASM 2 string into a circuit."""
    text = qasm.strip()
    errors = []
    try:
        from qiskit import qasm3

        return qasm3.loads(text)
    except Exception as exc:  # noqa: BLE001 - fall back to qasm2
        errors.append(f"qasm3: {exc}")
    try:
        from qiskit import qasm2

        return qasm2.loads(text)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"qasm2: {exc}")
    raise ValueError(
        "Failed to parse circuit as OpenQASM 3 or 2. " + " | ".join(errors)
    )


def observable_to_sparse_pauli(observable: list) -> SparsePauliOp:
    """Convert ``[["ZZ", 1.0], ["XX", 0.5]]`` into a SparsePauliOp."""
    pairs = [(str(term), complex(coeff)) for term, coeff in observable]
    return SparsePauliOp.from_list(pairs)


def _check_shots(shots: int) -> None:
    limit = max_shots()
    if shots < 1:
        raise GuardError("shots must be >= 1")
    if shots > limit:
        raise GuardError(f"shots={shots} exceeds GJQ_MAX_SHOTS={limit}")


def _check_submission_options(
    backend_name: str,
    optimization_level: int,
    amplitude_index: list[int] | None,
) -> None:
    if optimization_level not in range(4):
        raise GuardError("optimization_level must be between 0 and 3")
    if backend_name.upper() == "SAS-CPU" and amplitude_index is None:
        raise GuardError("SAS-CPU requires amplitude_index")


def _reserve_submission_slot() -> None:
    global _submission_count
    limit = max_submissions()
    with _submission_lock:
        if _submission_count >= limit:
            raise GuardError(
                f"Per-session submission limit reached "
                f"(GJQ_MAX_SUBMISSIONS_PER_SESSION={limit}). Restart the server "
                "to reset, or raise the limit if this is intentional."
            )
        _submission_count += 1


def _release_submission_slot() -> None:
    global _submission_count
    with _submission_lock:
        if _submission_count > 0:
            _submission_count -= 1


def submission_count() -> int:
    return _submission_count


def _extract_job_id(job: Any) -> str:
    """Read the task id from a RuntimeJob, isolating SDK internals.

    The SDK stores the id on the private ``_job_id`` attribute, annotated as
    ``list[str]`` but currently returning a single ``str``. Batch submission is
    planned SDK-side, so we normalize defensively: a single-element list/tuple is
    unwrapped to its one id, and a multi-element batch is rejected here (these
    submit helpers handle one circuit). Replace with the public ``job.job_id``
    once gjq-client exposes it.
    """
    raw = job._job_id
    if isinstance(raw, (list, tuple)):
        if len(raw) != 1:
            raise GuardError(
                f"Expected a single task id, got {len(raw)}; batch submission "
                "is not supported by these helpers."
            )
        raw = raw[0]
    if raw is None or not str(raw).strip():
        raise GuardError("The submitted job did not return a valid task id.")
    return str(raw)


def _prepare_circuit(
    backend: Any,
    qasm: str,
    transpile: bool,
    optimization_level: int,
) -> QuantumCircuit:
    circuit = qasm_to_circuit(qasm)
    if transpile:
        pm = generate_preset_pass_manager(
            backend=backend, optimization_level=optimization_level
        )
        circuit = pm.run(circuit)
    return circuit


def submit_sample(
    backend_name: str,
    qasm: str,
    shots: int = 1024,
    optimization_level: int = 1,
    transpile: bool = True,
    amplitude_index: list[int] | None = None,
) -> str:
    """Submit a sampling task; returns the task_id (instanceId)."""
    _check_shots(shots)
    _check_submission_options(backend_name, optimization_level, amplitude_index)
    service = get_service()
    backend = service.backend(backend_name)
    if backend is None:
        raise GuardError(f"Backend '{backend_name}' not found or unavailable.")
    circuit = _prepare_circuit(backend, qasm, transpile, optimization_level)
    _reserve_submission_slot()
    sampler = Sampler(backend=backend)
    try:
        job = sampler.run(circuit, shots=shots, amplitude_index=amplitude_index)
        return _extract_job_id(job)
    except Exception:
        _release_submission_slot()
        raise


def submit_estimate(
    backend_name: str,
    qasm: str,
    observable: list,
    shots: int = 1024,
    optimization_level: int = 1,
    transpile: bool = True,
    amplitude_index: list[int] | None = None,
) -> str:
    """Submit an estimation task; returns the task_id (instanceId)."""
    _check_shots(shots)
    _check_submission_options(backend_name, optimization_level, amplitude_index)
    obs = observable_to_sparse_pauli(observable)
    service = get_service()
    backend = service.backend(backend_name)
    if backend is None:
        raise GuardError(f"Backend '{backend_name}' not found or unavailable.")
    circuit = _prepare_circuit(backend, qasm, transpile, optimization_level)
    _reserve_submission_slot()
    estimator = Estimator(backend=backend)
    try:
        job = estimator.run(circuit, shots=shots, obs=obs, amplitude_index=amplitude_index)
        return _extract_job_id(job)
    except Exception:
        _release_submission_slot()
        raise


def task_status(task_id: str) -> str | None:
    """Non-blocking status lookup via the service (no busy-poll)."""
    return get_service().task_status(task_id)


def task_result(task_id: str, observable: list | None = None) -> Any:
    """Non-blocking result lookup.

    Returns ``{}`` while the task is still running (service-level behaviour),
    avoiding the busy-poll loop in RuntimeJob.wait_for_final_state.
    """
    obs = observable_to_sparse_pauli(observable) if observable else None
    return get_service().task_result(task_id, obs=obs)


# NOTE: The functions below reach into gjq-client internals (``service._client``,
# and ``job._job_id`` in the submit_* functions) because GJQRuntimeService /
# RuntimeJob expose no public equivalents for these operations. Re-verify against
# the SDK whenever bumping gjq-client (pyproject pins it to <0.2 for this reason).
def task_log(task_id: str) -> str:
    return get_service()._client.task_log(task_id).get("log")


def task_detail(task_id: str) -> dict:
    return get_service()._client.task_detail(task_id)


def list_backends() -> list[dict]:
    return get_service().list_backends()


def backend_configuration(backend_name: str) -> dict:
    return get_service()._client.backend_configuration(backend_name)


def backend_properties(backend_name: str) -> dict | None:
    return get_service()._client.backend_properties(backend_name)


def least_busy_backend_name() -> str:
    backend = get_service().least_busy()
    return backend.name


def list_tasks() -> list[dict]:
    return get_service().list_tasks()
