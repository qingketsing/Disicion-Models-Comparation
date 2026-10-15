import json
from unittest.mock import patch

import pytest

from orchestration.jev_local_driver import check_resume


@pytest.mark.parametrize("code,allowed", [(499, True), (401, False), (429, False)])
def test_explicit_restart_allows_only_inspected_http499(tmp_path, code, allowed):
    directory = tmp_path / "interrupted"
    directory.mkdir()
    (directory / "manifest.json").write_text(json.dumps({"state": "interrupted"}))
    (directory / "requests.jsonl").write_text(
        json.dumps({"status": "http_error", "http_status": code}) + "\n"
    )
    state = {
        "jobs": {
            "main": {
                "state": "interrupted",
                "error_type": "WatchdogHTTPStop",
                "run_dir": "interrupted",
            }
        }
    }
    spec = {"jobs": [{"id": "main"}]}
    with pytest.raises(ValueError):
        check_resume(spec, state, tmp_path)
    if allowed:
        check_resume(spec, state, tmp_path, reviewed_http499=True)
    else:
        with pytest.raises(ValueError, match="HTTP499"):
            check_resume(spec, state, tmp_path, reviewed_http499=True)


def test_resume_verifies_completed_evidence_and_accepts_transport_stop(tmp_path):
    spec = {"jobs": [{"id": "checkpoint"}, {"id": "main"}]}
    state = {
        "jobs": {
            "checkpoint": {"state": "completed", "run_dir": "old-checkpoint"},
            "main": {"state": "interrupted", "error_type": "WatchdogTransportStop"},
        }
    }
    with patch("orchestration.jev_local_driver.completed_entry", return_value=True) as verify:
        with patch("orchestration.jev_local_driver.audit_run") as audit:
            check_resume(spec, state, tmp_path)
            verify.assert_called_once()
            audit.assert_called_once_with(tmp_path / "old-checkpoint")


@pytest.mark.parametrize(
    "entry",
    [
        {"state": "running"},
        {"state": "failed", "error_type": "UnknownError"},
        {"state": "interrupted", "error_type": "KeyboardInterrupt"},
    ],
)
def test_resume_rejects_unreviewed_attempts(tmp_path, entry):
    with pytest.raises(ValueError, match="unreviewed"):
        check_resume({"jobs": [{"id": "main"}]}, {"jobs": {"main": entry}}, tmp_path)


def test_resume_rejects_modified_completion(tmp_path):
    with patch("orchestration.jev_local_driver.completed_entry", return_value=False):
        with pytest.raises(ValueError, match="evidence changed"):
            check_resume(
                {"jobs": [{"id": "main"}]}, {"jobs": {"main": {"state": "completed"}}}, tmp_path
            )
