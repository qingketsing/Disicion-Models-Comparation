"""Wait for the current Jev pilot, then perform bounded capacity confirmation."""

import argparse
import ctypes
import getpass
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from decisionbench.analysis import audit_run, read_json
from decisionbench.artifacts import file_hash, write_json
from decisionbench.suite import completed_entry, verify_bundle
from orchestration.prepare_jev_capacity import QuotaBudgetExceeded, create_jev_capacity_bundle
from orchestration.qwen_report import steady_windows


def alive(pid):
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
    from ctypes import wintypes

    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        if ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: no such PID
            return False
        raise OSError(ctypes.get_last_error(), 'cannot verify pilot process')
    try:
        code = wintypes.DWORD()
        if not api.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise OSError(ctypes.get_last_error(), 'cannot read pilot process state')
        return code.value == 259  # STILL_ACTIVE
    finally:
        api.CloseHandle(handle)


def assess_rates(path, root):
    plan = read_json(path)
    verify_bundle(plan, root)
    state = read_json(root / 'results/suites' / file_hash(path) / 'index.json')
    grouped = defaultdict(list)
    for job in plan['jobs']:
        if job['model'] != 'jev' or job['block'] != 'load':
            continue
        entry = state['jobs'].get(job['id'], {})
        if not completed_entry(entry, job, root):
            raise ValueError('load evidence is incomplete or changed')
        directory = root / entry['run_dir']
        manifest, rows, _, summary, _, cost = audit_run(directory)
        for source, digest in manifest['source_files'].items():
            if file_hash(directory / 'source' / source) != digest:
                raise ValueError('load source snapshot differs')
        windows = steady_windows(rows, manifest['config']['duration_s'])
        grouped[summary['offered_rps']].append(dict(
            job=job['id'], run=entry['run_dir'], duration_s=manifest['config']['duration_s'],
            passed=summary['slo_capacity_candidate'] and all(w['passed'] for w in windows),
            p95_ms=summary['latency_attempted']['p95_ms'],
            success_rate=summary['success_rate'], max_scheduler_lag_ms=summary['scheduler_lag']['max_ms'],
            status_counts=summary['status_counts'], network_retry=summary['network_retry'],
            cost=cost, windows=windows,
        ))
    return {rate: dict(runs=items, all_repeats_pass=len(items)==3 and all(x['passed'] for x in items))
            for rate, items in grouped.items()}


def formal_selection(rates):
    passing = [rate for rate, result in rates.items() if result['all_repeats_pass']]
    if not passing:
        return [1], 'No pilot rate passed; confirm the minimum tested offered rate without lowering thresholds.'
    candidate = max(passing)
    failing = [rate for rate, result in rates.items()
               if rate > candidate and not result['all_repeats_pass']]
    return [candidate] + ([min(failing)] if failing else []), 'Highest passing rate and nearest higher tested failure.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot', type=Path, required=True)
    parser.add_argument('--pilot-status', type=Path, required=True)
    parser.add_argument('--prefix', type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd()
    status_path = Path(str(args.prefix) + '-status.json')
    log_path = Path(str(args.prefix) + '-driver.log')
    if status_path.exists() or log_path.exists():
        raise SystemExit('capacity driver already exists; inspect before starting')
    verify_bundle(read_json(args.pilot), root)
    initial = read_json(args.pilot_status)
    if initial['plan_sha256'] != file_hash(args.pilot):
        raise SystemExit('pilot status references a different frozen plan')
    key = (getpass.getpass('Runtime Jev credential: ') if sys.stdin.isatty()
           else sys.stdin.readline()).strip()
    if not key.startswith('apikey_'):
        raise SystemExit('missing runtime credential')
    env = dict(os.environ, TYPESAFE_API_KEY=key, PYTHONUTF8='1', PYTHONUNBUFFERED='1',
               HTTP_PROXY='http://127.0.0.1:7897', HTTPS_PROXY='http://127.0.0.1:7897',
               ALL_PROXY='http://127.0.0.1:7897', NO_PROXY='127.0.0.1,localhost,::1')
    evidence = dict(state='waiting_for_pilot', pid=os.getpid(), pilot_driver_pid=initial['driver_pid'],
                    started_at_utc=datetime.now(timezone.utc).isoformat(),
                    plans=[str(args.pilot)], stages=[],
                    policy='Three repeats; 500ms/.99/20ms and every60s window; original retry3; '
                    'quota-screened expansion only after8 passes; minimum1RPS confirmation if no pass; '
                    'no automatic retry of failed suites; existing main baselines reused.')
    status_path.parent.mkdir(parents=True, exist_ok=True)

    def save():
        write_json(status_path, evidence)

    save()
    with log_path.open('x', encoding='utf-8') as log:
        def execute(rates, duration, tag):
            name = f'massive-jev-local-v4-retry3-{tag}'
            target = create_jev_capacity_bundle(
                (root / args.pilot).resolve(), root, root / 'experiments' / name, rates, duration
            )
            relative = str(target.relative_to(root))
            evidence['plans'].append(relative)
            evidence.update(state='running', active_plan=relative)
            save()
            command = [sys.executable, '-m', 'orchestration.stage_watchdog', '--model', 'jev',
                       '--block', 'load', '--plan', relative, '--stop-invalid', '--stop-transport-error',
                       '--log-prefix', str(args.prefix) + '-' + tag]
            child = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=log,
                                     stderr=log, text=True)
            evidence['watchdog_launcher_pid'] = child.pid
            save()
            child.communicate(key + '\n')
            if child.returncode:
                raise RuntimeError('Jev capacity watchdog stopped; inspect evidence before any restart')
            results = assess_rates(target, root)
            evidence['stages'].append(dict(plan=relative,duration_s=duration,rates=results))
            save()
            return results

        try:
            deadline = time.monotonic() + 7200
            while True:
                current = read_json(args.pilot_status)
                if current['state'] == 'pilot_completed':
                    break
                if current['state'] == 'stopped' or not alive(initial['driver_pid']):
                    raise RuntimeError('pilot stopped before completion; no capacity requests sent')
                if time.monotonic() > deadline:
                    raise RuntimeError('pilot did not complete within two hours')
                time.sleep(10)
            rates = assess_rates(args.pilot, root)
            evidence['stages'].append(dict(plan=str(args.pilot), duration_s=120, rates=rates))
            evidence['state'] = 'pilot_audited'
            save()
            if rates.get(8, {}).get('all_repeats_pass'):
                for rate in (16, 32, 64):
                    try:
                        result = execute([rate], 120, f'extended{rate}')
                    except QuotaBudgetExceeded:
                        evidence['quota_limited_extension'] = dict(skipped_logical_rps=rate,
                            reason='Retry-amplified attempts or observed token budget exceed published quota; '
                            'no requests at this rate; no empirical capacity failure claimed.')
                        save()
                        break
                    rates.update(result)
                    if not result[rate]['all_repeats_pass']:
                        break
            selected, reason = formal_selection(rates)
            evidence.update(selected_formal_rates=selected, selection_reason=reason)
            save()
            results = execute(selected, 300, 'formal')
            tested = set(selected)
            confirmed = [rate for rate, result in results.items() if result['all_repeats_pass']]
            candidate = selected[0]
            while not results[candidate]['all_repeats_pass']:
                lower = [rate for rate, result in rates.items()
                         if rate < candidate and result['all_repeats_pass'] and rate not in tested]
                candidate = max(lower) if lower else 1
                if candidate in tested:
                    break
                results = execute([candidate], 300, f'formal-lower{candidate:g}')
                tested.add(candidate)
                confirmed += [r for r, v in results.items() if v['all_repeats_pass']]
            evidence.update(state='completed', confirmed_capacity_rps=max(confirmed) if confirmed else None,
                            finished_at_utc=datetime.now(timezone.utc).isoformat())
            save()
        except BaseException as exc:
            evidence.update(state='stopped',error_type=type(exc).__name__,
                            finished_at_utc=datetime.now(timezone.utc).isoformat())
            save()
            raise


if __name__ == '__main__':
    main()
