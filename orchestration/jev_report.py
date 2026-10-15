"""Audit completed Jev suites and export quality, windows, retries and known costs."""

import argparse
from pathlib import Path

from decisionbench.analysis import write_csv
from decisionbench.artifacts import write_json
from decisionbench.metrics import request_cost
from orchestration.qwen_report import analyze, load_runs


def retry_cost_evidence(runs, out):
    summary, attempts, recovered = [], [], []
    for run in runs:
        for scope,rows in [('measurement',run['rows']),('warmup',run['warmup'])]:
            known_cost = request_cost(rows,run['manifest']['elapsed_s'],run['cost']['pricing'],500)
            call_count=transport_failures=additional=recovered_count=0
            for row in rows:
                network = row.get('network_attempts', [])
                call_count += len(network)
                additional += max(0,len(network)-1)
                if row['dispatch_s'] is not None and not network:
                    raise ValueError('retry3 run is missing actual attempt evidence')
                for attempt in network:
                    transport_failures += attempt['status'] in {'network_error','timeout'}
                    attempts.append(dict(
                        job=run['job']['id'],run=run['entry']['run_dir'],scope=scope,
                        request_id=row['request_id'],sample_id=row['sample_id'],
                        attempt=attempt['attempt'],status=attempt['status'],
                        error_type=attempt.get('error_type'),started_s=attempt['started_s'],
                        completed_s=attempt.get('completed_s'),retry_backoff_s=attempt.get('retry_backoff_s',0),
                        usage_unknown=attempt.get('usage_unknown',False),
                    ))
                if row['status']=='ok' and len(network)>1:
                    recovered_count += 1
                    recovered.append(dict(job=run['job']['id'],scope=scope,
                                          request_id=row['request_id'],sample_id=row['sample_id'],
                                          attempts=len(network),e2e_latency_ms=row['e2e_latency_ms'],
                                          slo_pass=row['e2e_latency_ms']<=500))
            summary.append(dict(job=run['job']['id'],run=run['entry']['run_dir'],scope=scope,
                                logical_requests=len(rows),adapter_attempts=call_count,
                                additional_attempts=additional,transport_failures=transport_failures,
                                recovered_requests=recovered_count,known_cost_usd=known_cost['total_measured_cost'],
                                usage_complete=known_cost['usage_complete']))
    write_csv(out/'network-retry-summary.csv',summary)
    write_csv(out/'network-attempts.csv',attempts)
    write_csv(out/'recovered-requests.csv',recovered)
    totals={}
    for scope in ['measurement','warmup']:
        part=[r for r in summary if r['scope']==scope]
        totals[scope]={key:sum(r[key] for r in part) for key in
                       ['logical_requests','adapter_attempts','additional_attempts','transport_failures',
                        'recovered_requests','known_cost_usd']}
        totals[scope]['usage_complete']=all(r['usage_complete'] for r in part)
    write_json(out/'network-retry-cost-audit.json',dict(
        totals=totals,scope='Distinct completed Jev runs in supplied plans; baselines deduplicated.',
        excluded='Synthetic probes and old/interrupted attempts require separate historical ledger.',
        limitations='Failed transport attempts may have billed unknown usage; known costs are lower bounds '
        'whenever usage_complete=false. Recovered logical success does not mean no network failure.',
    ))
    return totals


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,action='append',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    root=Path.cwd()
    plans=[p.resolve() for p in args.plan]
    out=args.out.resolve()
    # Reject incomplete plans before writing an apparent final report.
    runs=load_runs(plans,root,'jev')
    analyze(plans,root,out,'jev')
    print(retry_cost_evidence(runs,out))


if __name__=='__main__':
    main()
