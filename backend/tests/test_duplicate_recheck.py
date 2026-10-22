import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_complaints import fields, submit

from app.algorithms.duplicate_detection.text_similarity import TEXT_ENGINE


def test_recheck_cli_readonly_dry_run_bounded_resume_and_model_versions(
    complaint_client, complaint_app
):
    first = submit(complaint_client, fields()).json()["complaintId"]
    second = submit(complaint_client, fields(latitude="12.97161")).json()["complaintId"]
    settings = complaint_app.state.settings
    environment = os.environ | {
        "APP_ENV": "test",
        "AUTH_PROVIDER": "local",
        "DEBUG": "false",
        "COMPLAINT_PROVIDER": "sqlite",
        "EVIDENCE_PROVIDER": "local",
        "LOCAL_DB_PATH": str(settings.local_db_path),
        "LOCAL_EVIDENCE_ROOT": str(settings.local_evidence_root),
        "AWS_EC2_METADATA_DISABLED": "true",
    }

    def run(*args):
        result = subprocess.run(
            [sys.executable, "-m", "app.scripts.recheck_duplicates", *args],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return [json.loads(line) for line in result.stdout.splitlines()]

    before = hashlib.sha256(settings.local_db_path.read_bytes()).hexdigest()
    result = run("--dry-run", "--limit", "1")
    assert result[0]["dryRun"] and len(result[0]["ids"]) == 1
    assert hashlib.sha256(settings.local_db_path.read_bytes()).hexdigest() == before
    result = run("--limit", "1")
    assert result[-1]["processed"] == 1
    result = run("--limit", "1", "--after", result[-1]["nextAfter"])
    assert result[-1]["processed"] == 1
    repository = complaint_app.state.duplicate_detection_service.repository
    assert (
        repository.job(first)["state"] == "COMPLETE"
        and repository.job(second)["state"] == "COMPLETE"
    )
    config = complaint_app.state.duplicate_detection_service.config.version
    assert repository.historical_ids("", 10, config, TEXT_ENGINE.version) == []
    assert set(repository.historical_ids("", 10, config, "changed-model-version")) == {
        first,
        second,
    }
    assert run("--only-outdated", "--limit", "10")[-1]["processed"] == 0
