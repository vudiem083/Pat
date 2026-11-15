from __future__ import annotations

import json
import threading
import time

import pytest

from bat.config import Settings
from bat.core.errors import make_error
from bat.core.models import JobStatus
from bat.services import BatServices


@pytest.fixture()
def job_services(settings: Settings):
    service_layer = BatServices(settings.with_overrides(job_workers=2))
    yield service_layer
    service_layer.shutdown()


def _wait_status(services: BatServices, job_id: str, wanted: set[str], timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = services.jobs.get(job_id)
        if job.status in wanted:
            return job
        time.sleep(0.05)
    return services.jobs.get(job_id)


def test_validate_job_completes_with_report(job_services: BatServices, addon_project: str):
    job = job_services.jobs.submit("VALIDATE", project_id=addon_project)
    result = job_services.jobs.wait(job.job_id, timeout=10)
    assert result["completed"] is True
    finished = job_services.jobs.get(job.job_id)
    assert finished.status == JobStatus.COMPLETED.value
    assert finished.result["report"]["project_id"] == addon_project
    report = job_services.jobs.report(job.job_id)
    assert report["status"] == "COMPLETED"
    assert report["duration_seconds"] is not None


def test_job_logs_are_structured(job_services: BatServices, addon_project: str):
    job = job_services.jobs.submit("VALIDATE", project_id=addon_project)
    job_services.jobs.wait(job.job_id, timeout=10)
    logs = job_services.jobs.logs(job.job_id)
    assert logs["total_lines"] >= 2
    messages = [line["message"] for line in logs["lines"]]
    assert any("started" in m.lower() for m in messages)
    assert any("finished" in m.lower() for m in messages)
    assert all("timestamp" in line for line in logs["lines"])


def test_bat_error_becomes_failed_job_with_code(job_services: BatServices):
    job = job_services.jobs.submit(
        "DIAGNOSE", params={"incident_id": "incident_does_not_exist"}
    )
    job_services.jobs.wait(job.job_id, timeout=10)
    finished = job_services.jobs.get(job.job_id)
    assert finished.status == JobStatus.FAILED.value
    assert finished.error_code == "BAT-NOTFOUND-006"


def test_unhandled_exception_is_recorded_not_swallowed(job_services: BatServices):
    def explode(_ctx):
        raise RuntimeError("boom")

    job_services.jobs.register("BUILD", explode)
    job = job_services.jobs.submit("BUILD")
    job_services.jobs.wait(job.job_id, timeout=10)
    finished = job_services.jobs.get(job.job_id)
    assert finished.status == JobStatus.FAILED.value
    assert finished.error_code == "BAT-JOB-004"
    assert "boom" in (finished.message or "")
    assert finished.result["error"]["type"] == "RuntimeError"


def test_unknown_job_type_rejected(job_services: BatServices):
    with pytest.raises(Exception) as exc:
        job_services.jobs.submit("NOT_A_JOB")
    assert getattr(exc.value, "code", "") == "BAT-INPUT-001"


def test_wait_timeout_does_not_cancel(job_services: BatServices):
    release = threading.Event()

    def slow(_ctx):
        release.wait(timeout=5)
        return {"done": True}

    job_services.jobs.register("BUILD", slow)
    job = job_services.jobs.submit("BUILD")
    early = job_services.jobs.wait(job.job_id, timeout=0.2)
    assert early["completed"] is False
    assert job_services.jobs.get(job.job_id).status in {
        JobStatus.QUEUED.value,
        JobStatus.STARTING.value,
        JobStatus.RUNNING.value,
    }
    release.set()
    final = job_services.jobs.wait(job.job_id, timeout=10)
    assert final["completed"] is True
    assert final["job"]["status"] == JobStatus.COMPLETED.value


def test_explicit_cancel_of_queued_job(settings: Settings):
    service_layer = BatServices(settings.with_overrides(job_workers=1))
    try:
        gate = threading.Event()

        def blocking(_ctx):
            gate.wait(timeout=5)
            return {}

        service_layer.jobs.register("BUILD", blocking)
        first = service_layer.jobs.submit("BUILD")
        _wait_status(service_layer, first.job_id, {JobStatus.RUNNING.value, JobStatus.STARTING.value})
        second = service_layer.jobs.submit("BUILD")
        cancelled = service_layer.jobs.cancel(second.job_id)
        assert cancelled.status == JobStatus.CANCELLED.value
        assert cancelled.error_code == "BAT-JOB-001"
        gate.set()
        service_layer.jobs.wait(first.job_id, timeout=10)
        with pytest.raises(Exception) as exc:
            service_layer.jobs.cancel(first.job_id)
        assert getattr(exc.value, "code", "") == "BAT-JOB-001"
    finally:
        service_layer.shutdown()


def test_job_timeout_is_recorded_as_timed_out(job_services: BatServices):
    def sleep_long(_ctx):
        time.sleep(2)
        return {"late": True}

    job_services.jobs.register("BUILD", sleep_long)
    job = job_services.jobs.submit("BUILD", timeout_seconds=0.3)
    finished = _wait_status(job_services, job.job_id, {JobStatus.TIMED_OUT.value}, timeout=5)
    assert finished.status == JobStatus.TIMED_OUT.value
    assert finished.error_code == "BAT-RUNTIME-005"
    time.sleep(2.2)  # let the handler finish; it must not overwrite TIMED_OUT
    assert job_services.jobs.get(job.job_id).status == JobStatus.TIMED_OUT.value


def test_orphaned_running_job_is_recovered_as_crashed(job_services: BatServices):
    from bat.core.models import Job

    orphan = Job(
        project_id=None,
        job_type="BUILD",
        status=JobStatus.RUNNING.value,
        started_at="2026-01-01T00:00:00Z",
    )
    job_services.db.save_job(orphan)
    recovered = job_services.jobs.recover_orphans()
    assert orphan.job_id in recovered
    restored = job_services.jobs.get(orphan.job_id)
    assert restored.status == JobStatus.CRASHED.value
    assert restored.error_code == "BAT-JOB-002"


def test_heartbeat_file_written_during_job(job_services: BatServices):
    gate = threading.Event()

    def slow(_ctx):
        gate.wait(timeout=5)
        return {}

    job_services.jobs.register("BUILD", slow)
    job = job_services.jobs.submit("BUILD")
    time.sleep(0.4)
    heartbeat = job_services.jobs.heartbeat_path(job.job_id)
    assert heartbeat.exists()
    payload = json.loads(heartbeat.read_text())
    assert payload["job_id"] == job.job_id
    gate.set()
    job_services.jobs.wait(job.job_id, timeout=10)


def test_job_aborted_maps_to_requested_status(job_services: BatServices):
    from bat.jobs.state import JobAborted

    def crash(_ctx):
        raise JobAborted("BAT-RUNTIME-001", "process died", status="CRASHED", result={"x": 1})

    job_services.jobs.register("BUILD", crash)
    job = job_services.jobs.submit("BUILD")
    job_services.jobs.wait(job.job_id, timeout=10)
    finished = job_services.jobs.get(job.job_id)
    assert finished.status == JobStatus.CRASHED.value
    assert finished.error_code == "BAT-RUNTIME-001"
    assert finished.result["x"] == 1


def test_submitting_after_shutdown_is_refused(settings: Settings):
    service_layer = BatServices(settings)
    service_layer.jobs.shutdown()
    with pytest.raises(Exception) as exc:
        service_layer.jobs.submit("VALIDATE")
    assert getattr(exc.value, "code", "") == "BAT-JOB-003"
    service_layer.shutdown()
