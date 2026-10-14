import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# External watchdog: records controls, never changes requests or repairs results.
p = argparse.ArgumentParser()
p.add_argument("--model", choices=["qwen", "jev"], required=True)
p.add_argument("--block", choices=["main", "load", "scale"], required=True)
p.add_argument(
    "--plan", type=Path, default=Path("experiments/massive-split-constrained-pilot-v3/plan.json")
)
p.add_argument("--log-prefix", type=Path)
p.add_argument("--retry-failed", action="store_true")
p.add_argument("--stop-invalid", action="store_true", help="Stop on any invalid output")
a = p.parse_args()
root = Path.cwd()
plan = (root / a.plan).resolve()

state = root / "results/suites" / hashlib.sha256(plan.read_bytes()).hexdigest() / "index.json"
out = a.log_prefix or root / "results/execution-20261014" / f"v3-{a.model}-{a.block}"
out.parent.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
if a.model == "jev":
    key = sys.stdin.readline().strip()
    if not key.startswith("apikey_"):
        raise SystemExit("missing runtime credential")
    env.update(
        TYPESAFE_API_KEY=key,
        HTTP_PROXY="http://127.0.0.1:7897",
        HTTPS_PROXY="http://127.0.0.1:7897",
        NO_PROXY="127.0.0.1,localhost,::1",
    )
cmd = [
    sys.executable,
    "-m",
    "decisionbench.suite",
    "run",
    "--plan",
    str(plan),
    "--block",
    a.block,
    "--model",
    a.model,
    "--execute",
]
if a.retry_failed:
    cmd += ["--retry-failed"]
if a.model == "jev":
    spec = json.loads(plan.read_text(encoding="utf-8"))
    budget = sum(
        j["api_requests_upper_bound"]
        for j in spec["jobs"]
        if j["model"] == a.model and j["block"] == a.block
    )
    cmd += ["--max-api-requests", str(budget)]
control = {
    "policy": "stop on any HTTP error, any adapter error, or three consecutive transport/timeouts",
    "stop_invalid_output": a.stop_invalid,
    "model": a.model,
    "block": a.block,
    "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
with Path(str(out) + ".log").open("x", encoding="utf-8") as log:
    child = subprocess.Popen(cmd, env=env, stdout=log, stderr=log)
    control["pid"] = child.pid
    Path(str(out) + "-watchdog.json").write_text(json.dumps(control, indent=2), encoding="utf-8")
    while child.poll() is None:
        time.sleep(2)
        try:
            s = json.loads(state.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        for j, e in s["jobs"].items():
            if (
                e["state"] != "running"
                or not j.startswith(a.block + "-")
                or not j.endswith("-" + a.model)
                or not e.get("run_dir")
            ):
                continue
            d = root / e["run_dir"]
            for name in ("warmup_requests.jsonl", "requests.jsonl"):
                f = d / name
                if not f.exists():
                    continue
                rows = []
                for line in f.read_text(encoding="utf-8").splitlines():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
                fatal = {"http_error", "adapter_error"}
                if a.stop_invalid:
                    fatal.add("invalid_output")
                bad = next((x for x in rows if x["status"] in fatal), None)
                if (
                    not bad
                    and len(rows) >= 3
                    and all(x["status"] in ("network_error", "timeout") for x in rows[-3:])
                ):
                    bad = rows[-1]
                if bad:
                    control.update(
                        stopped_for={
                            "job": j,
                            "file": name,
                            "status": bad["status"],
                            "http_status": bad["http_status"],
                        }
                    )
                    if os.name == "nt":
                        # Windows venv launchers may own an additional Python child.
                        subprocess.run(
                            ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                            check=True,
                            capture_output=True,
                        )
                    else:
                        child.send_signal(signal.SIGINT)
                    break
            if "stopped_for" in control:
                break
        if "stopped_for" in control:
            break
    try:
        code = child.wait(timeout=40)
    except subprocess.TimeoutExpired:
        child.kill()
        code = child.wait()
    control.update(exit_code=code, finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    Path(str(out) + "-watchdog.json").write_text(json.dumps(control, indent=2), encoding="utf-8")
    print(json.dumps(control, indent=2))
    raise SystemExit(code)
