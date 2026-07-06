"""Smoke tests for the gjq-runtime MCP server.

Offline tests cover circuit/observable parsing, guards, and tool registration
via an in-memory FastMCP client. A network integration test against the test
environment is opt-in via GJQ_RUN_INTEGRATION=1.
"""

import os

import pytest
from fastmcp import Client

from gjq_runtime_mcp_server import mcp
from gjq_runtime_mcp_server import runtime


EXPECTED_TOOLS = {
    "setup_gjq_account_tool",
    "active_account_info_tool",
    "list_backends_tool",
    "get_backend_configuration_tool",
    "get_backend_properties_tool",
    "least_busy_tool",
    "sample_tool",
    "estimate_tool",
    "get_task_status_tool",
    "get_task_result_tool",
    "get_task_log_tool",
    "get_task_detail_tool",
    "list_my_tasks_tool",
}


# --------------------------------------------------------------------------
# Offline: helpers and guards
# --------------------------------------------------------------------------


def test_qasm_to_circuit_qasm2():
    qasm = (
        'OPENQASM 2.0;\ninclude "qelib1.inc";\n'
        "qreg q[2];\ncreg c[2];\nh q[0];\ncx q[0],q[1];\n"
        "measure q[0] -> c[0];\nmeasure q[1] -> c[1];\n"
    )
    qc = runtime.qasm_to_circuit(qasm)
    assert qc.num_qubits == 2


def test_qasm_to_circuit_invalid():
    with pytest.raises(ValueError):
        runtime.qasm_to_circuit("not a circuit")


def test_observable_to_sparse_pauli():
    op = runtime.observable_to_sparse_pauli([["ZZ", 1.0], ["XX", 0.5]])
    assert op.num_qubits == 2


def test_shots_guard():
    with pytest.raises(runtime.GuardError):
        runtime._check_shots(0)
    with pytest.raises(runtime.GuardError):
        runtime._check_shots(runtime.max_shots() + 1)
    runtime._check_shots(1)  # ok


def test_active_account_info_masks_key(tmp_path, monkeypatch):
    cfg = tmp_path / "gjq_client_account.json"
    cfg.write_text(
        '{"channel": "gjq_cloud", "api_key": "abcd1234ef", "base_url": null, '
        '"backend_url": null}',
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "ACCOUNT_CONFIG_FILE", cfg)
    info = runtime.active_account_info()
    assert info["configured"] is True
    assert info["api_key"] != "abcd1234ef"
    assert "***" in info["api_key"]


# --------------------------------------------------------------------------
# Offline: tool registration via in-memory client
# --------------------------------------------------------------------------


async def test_tools_registered():
    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
    assert EXPECTED_TOOLS.issubset(tools)


async def test_example_circuit_resource():
    async with Client(mcp) as client:
        result = await client.read_resource("circuits://bell-state")
    text = result[0].text
    assert "OPENQASM" in text
    assert "cx q[0],q[1]" in text


async def test_get_task_result_pending(monkeypatch):
    monkeypatch.setattr(runtime, "task_result", lambda task_id, observable=None: {})
    monkeypatch.setattr(runtime, "task_status", lambda task_id: "RUNNING")
    async with Client(mcp) as client:
        res = await client.call_tool("get_task_result_tool", {"task_id": "x"})
    assert res.data["pending"] is True
    assert res.data["task_status"] == "RUNNING"
    assert res.data["result"] == {}


async def test_get_task_result_done(monkeypatch):
    monkeypatch.setattr(
        runtime, "task_result", lambda task_id, observable=None: {"00": 512}
    )
    monkeypatch.setattr(runtime, "task_status", lambda task_id: "DONE")
    async with Client(mcp) as client:
        res = await client.call_tool("get_task_result_tool", {"task_id": "x"})
    assert res.data["pending"] is False
    assert res.data["task_status"] == "DONE"
    assert res.data["result"] == {"00": 512}


async def test_get_task_result_done_empty_result(monkeypatch):
    monkeypatch.setattr(runtime, "task_result", lambda task_id, observable=None: {})
    monkeypatch.setattr(runtime, "task_status", lambda task_id: "DONE")
    async with Client(mcp) as client:
        res = await client.call_tool("get_task_result_tool", {"task_id": "x"})
    assert res.data["pending"] is False
    assert res.data["task_status"] == "DONE"
    assert res.data["result"] == {}


def test_submit_sample_rolls_back_submission_slot_on_submit_error(monkeypatch):
    class DummyService:
        def backend(self, backend_name):
            return object()

    class BrokenSampler:
        def __init__(self, backend):
            pass

        def run(self, *args, **kwargs):
            raise RuntimeError("submit failed")

    monkeypatch.setattr(runtime, "_submission_count", 0)
    monkeypatch.setattr(runtime, "get_service", lambda: DummyService())
    monkeypatch.setattr(runtime, "_prepare_circuit", lambda *args, **kwargs: object())
    monkeypatch.setattr(runtime, "Sampler", BrokenSampler)

    with pytest.raises(RuntimeError, match="submit failed"):
        runtime.submit_sample("dummy", "OPENQASM 2.0;")
    assert runtime.submission_count() == 0


def test_submit_estimate_rolls_back_submission_slot_on_submit_error(monkeypatch):
    class DummyService:
        def backend(self, backend_name):
            return object()

    class BrokenEstimator:
        def __init__(self, backend):
            pass

        def run(self, *args, **kwargs):
            raise RuntimeError("submit failed")

    monkeypatch.setattr(runtime, "_submission_count", 0)
    monkeypatch.setattr(runtime, "get_service", lambda: DummyService())
    monkeypatch.setattr(runtime, "_prepare_circuit", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        runtime, "observable_to_sparse_pauli", lambda observable: object()
    )
    monkeypatch.setattr(runtime, "Estimator", BrokenEstimator)

    with pytest.raises(RuntimeError, match="submit failed"):
        runtime.submit_estimate("dummy", "OPENQASM 2.0;", [["Z", 1.0]])
    assert runtime.submission_count() == 0


# --------------------------------------------------------------------------
# Opt-in network integration (test environment)
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("GJQ_RUN_INTEGRATION") != "1",
    reason="set GJQ_RUN_INTEGRATION=1 to run network integration test",
)
async def test_integration_bell_state():
    import asyncio

    from gjq_runtime_mcp_server import circuits

    async with Client(mcp) as client:
        backends = await client.call_tool("list_backends_tool", {})
        assert backends.data["status"] == "success"

        submitted = await client.call_tool(
            "sample_tool",
            {
                "qasm": circuits.BELL_STATE,
                "backend_name": "FAS-CPU",
                "shots": 1024,
            },
        )
        assert submitted.data["status"] == "success"
        task_id = submitted.data["task_id"]

        result = {}
        for _ in range(60):
            status = await client.call_tool("get_task_status_tool", {"task_id": task_id})
            if status.data["task_status"] == "DONE":
                res = await client.call_tool(
                    "get_task_result_tool", {"task_id": task_id}
                )
                result = res.data["result"]
                break
            await asyncio.sleep(2)
        assert result
