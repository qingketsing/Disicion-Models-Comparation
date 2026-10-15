"""Run a Jev suite; credentials stay in memory and transport failures stop execution."""

import argparse
import getpass
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from decisionbench.analysis import audit_run
from decisionbench.config import load_config
from decisionbench.suite import completed_entry, verify_bundle


def check_resume(spec, state, root):
    """Reuse verified completions and allow only inspected transport interruptions."""
    jobs = {job["id"]: job for job in spec["jobs"]}
    if set(state["jobs"]) - set(jobs):
        raise ValueError("suite contains unknown jobs")
    for name, entry in state["jobs"].items():
        if entry["state"] == "completed":
            if not completed_entry(entry, jobs[name], root):
                raise ValueError(f"completed evidence changed: {name}")
            audit_run(root / entry["run_dir"])
        elif not (
            entry["state"] == "interrupted" and entry.get("error_type") == "WatchdogTransportStop"
        ):
            raise ValueError(f"unreviewed attempt cannot resume: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument(
        "--resume-transport",
        action="store_true",
        help="Preserve completed runs and restart inspected interrupted runs",
    )
    args = parser.parse_args()
    root = Path.cwd()
    spec = json.loads(args.plan.read_text(encoding="utf-8"))
    verify_bundle(spec, root)
    retries = max(load_config(root / job["config"]).network_retries for job in spec["jobs"])
    digest = hashlib.sha256(args.plan.read_bytes()).hexdigest()
    index = root / "results/suites" / digest / "index.json"
    if index.with_name("running.lock").exists():
        raise SystemExit("suite is locked; inspect the owning controller first")
    if args.resume_transport:
        if not index.exists():
            raise SystemExit("resume requires existing inspected suite state")
        existing = json.loads(index.read_text(encoding="utf-8"))
        if existing["plan_sha256"] != digest:
            raise SystemExit("resume plan hash mismatch")
        check_resume(spec, existing, root)
    elif index.exists():
        raise SystemExit("fresh driver requires an unused plan; inspect existing attempts first")
    status_path = Path(str(args.prefix) + "-status.json")
    log_path = Path(str(args.prefix) + "-driver.log")
    if status_path.exists() or log_path.exists():
        raise SystemExit("choose a fresh execution prefix")
    key = (
        getpass.getpass("Runtime Jev credential: ") if sys.stdin.isatty() else sys.stdin.readline()
    ).strip()
    if not key.startswith("apikey_"):
        raise SystemExit("missing runtime credential")
    env = dict(
        os.environ,
        TYPESAFE_API_KEY=key,
        PYTHONUTF8="1",
        PYTHONUNBUFFERED="1",
        HTTP_PROXY="http://127.0.0.1:7897",
        HTTPS_PROXY="http://127.0.0.1:7897",
        ALL_PROXY="http://127.0.0.1:7897",
        NO_PROXY="127.0.0.1,localhost,::1",
    )
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status = dict(
        state="preflight",
        driver_pid=os.getpid(),
        plan=str(args.plan),
        plan_sha256=digest,
        started_at_utc=datetime.now(timezone.utc).isoformat(),
        completed_blocks=[],
        stop_on_final_request_error=True,
        resume_transport=args.resume_transport,
        network_retries_per_request=retries,
    )

    def save():
        tmp = status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        tmp.replace(status_path)

    save()
    with log_path.open("x", encoding="utf-8") as log:
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.probe_jev",
                    "--out",
                    str(args.prefix) + "-probe.json",
                    "--network-retries",
                    str(retries),
                ],
                env=env,
                stdout=log,
                stderr=log,
                check=True,
            )
            for block in ("checkpoint", "main", "scale", "load"):
                if not any(job["block"] == block for job in spec["jobs"]):
                    continue
                status.update(state="running", block=block)
                command = [
                    sys.executable,
                    "-m",
                    "orchestration.stage_watchdog",
                    "--model",
                    "jev",
                    "--block",
                    block,
                    "--plan",
                    str(args.plan),
                    "--stop-invalid",
                    "--stop-transport-error",
                    "--log-prefix",
                    str(args.prefix) + "-" + block,
                ]
                if args.resume_transport:
                    command.append("--retry-failed")
                child = subprocess.Popen(
                    command, env=env, stdin=subprocess.PIPE, stdout=log, stderr=log, text=True
                )
                status["watchdog_launcher_pid"] = child.pid
                save()
                child.communicate(key + "\n")
                if child.returncode:
                    raise RuntimeError(
                        f"{block} watchdog exited {child.returncode}; inspect evidence"
                    )
                state = json.loads(index.read_text(encoding="utf-8"))
                for job in spec["jobs"]:
                    if job["block"] != block:
                        continue
                    entry = state["jobs"].get(job["id"], {})
                    if not completed_entry(entry, job, root):
                        raise RuntimeError(f"incomplete job: {job['id']}")
                    audited = audit_run(root / entry["run_dir"])
                    if any(
                        row["status"]
                        in {
                            "network_error",
                            "timeout",
                            "http_error",
                            "adapter_error",
                            "invalid_output",
                        }
                        for row in audited[1]
                    ):
                        raise RuntimeError(f"failed request in completed job: {job['id']}")
                status["completed_blocks"].append(block)
                save()
            status.update(state="pilot_completed")
        except Exception as exc:
            status.update(state="stopped", error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            status["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            save()


if __name__ == "__main__":
    main()
