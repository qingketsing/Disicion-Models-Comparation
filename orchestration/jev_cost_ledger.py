"""Account separately for completed, historical, interrupted, warmup and probe usage."""

import argparse
import json
from pathlib import Path

from decisionbench.analysis import read_json, write_csv
from decisionbench.artifacts import file_hash, write_json
from decisionbench.metrics import request_cost


def historical_ledger(root, current_runs, out):
    records = []
    for path in sorted((root/'results').glob('*/manifest.json')):
        manifest = read_json(path)
        if manifest['config']['adapter']['kind']!='jev' or manifest['synthetic']:
            continue
        if manifest['state']=='running':
            raise ValueError('Jev run still marked running; cannot finalize the historical cost ledger')
        directory=path.parent
        relative=str(directory.relative_to(root)).replace('\\','/')
        for source,digest in manifest['source_files'].items():
            if file_hash(directory/'source'/source)!=digest:
                raise ValueError('historical Jev source snapshot changed')
        cost_path=directory/'cost.json'
        pricing=read_json(cost_path)['pricing'] if cost_path.exists() else manifest['config']['cost']
        if pricing.get('currency')!='USD' or pricing.get('input_price_per_million')!=0.042 or pricing.get('output_price_per_million')!=0:
            raise ValueError('historical ledger requires explicit approved USD API pricing')
        for scope,name in [('measurement','requests.jsonl'),('warmup','warmup_requests.jsonl')]:
            source=directory/name
            if not source.exists():
                continue
            rows=[json.loads(line) for line in source.read_text(encoding='utf-8').splitlines()]
            if len({r['request_id'] for r in rows})!=len(rows):
                raise ValueError('duplicate request IDs in historical scope')
            cost=request_cost(rows,0,pricing,manifest['config']['slo_ms'])
            attempts=sum(len(r['network_attempts']) if 'network_attempts' in r else
                         int(r['dispatch_s'] is not None) for r in rows)
            records.append(dict(
                run=relative,phase='current_completed' if relative in current_runs else 'historical',
                lifecycle=manifest['state'],scope=scope,logical_requests=len(rows),
                adapter_attempts=attempts,legacy_attempt_counts_inferred=any('network_attempts' not in r for r in rows),
                final_non_ok=sum(r['status']!='ok' for r in rows),
                additional_attempts=sum(max(0,len(r.get('network_attempts',[]))-1) for r in rows),
                known_cost_usd=cost['total_measured_cost'],usage_complete=cost['usage_complete'],
                source_sha256=file_hash(source),
            ))
    probes=[]
    for path in sorted((root/'results/execution-20261014').glob('*probe*.json')):
        probe=read_json(path)
        if not probe.get('synthetic') or 'jev' not in path.name:
            continue
        steps=[s for s in probe.get('steps',[]) if s.get('path')=='/v1/systemone']
        transport=[a for a in probe.get('transport_attempts',[]) if a.get('path')=='/v1/systemone']
        input_tokens=output_tokens=0
        complete=bool(steps) and not any('error_type' in a or a.get('status')!=200 for a in transport)
        for step in steps:
            usage=step.get('response',{}).get('usage',{})
            complete &= usage.get('input_tokens') is not None and usage.get('output_tokens') is not None
            input_tokens += usage.get('input_tokens') or 0
            output_tokens += usage.get('output_tokens') or 0
        probes.append(dict(
            probe=str(path.relative_to(root)),post_attempts=len(transport) if transport else len(steps),
            usage_complete=complete,known_input_tokens=input_tokens,known_output_tokens=output_tokens,
            known_cost_usd=input_tokens*0.042/1_000_000,source_sha256=file_hash(path),
        ))
    write_csv(out/'historical-run-cost-ledger.csv',records)
    write_csv(out/'synthetic-probe-cost-ledger.csv',probes)
    summary=dict(known_run_cost_usd=sum(r['known_cost_usd'] for r in records),
                  known_probe_cost_usd=sum(p['known_cost_usd'] for p in probes),
                  usage_complete=all(r['usage_complete'] for r in records) and all(p['usage_complete'] for p in probes),
                  known_cost_total_usd=sum(r['known_cost_usd'] for r in records)+sum(p['known_cost_usd'] for p in probes),
                  run_scopes=records,probes=probes,
                  limitations='Known logged usage only, including old failed/interrupted attempts. '
                  'Legacy call counts inferred from dispatch; probe diagnostics without response usage are unknown. '
                  'Read-only GET diagnostics are not inference calls. No provider invoice or FX conversion. '
                  'Unknown failed attempt usage means total is a lower bound, even if subsequent retry succeeds.')
    write_json(out/'historical-cost-audit.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    audit=read_json(args.report/'audit.json')
    current={r['run'].replace('\\','/') for r in audit['runs']}
    result=historical_ledger(Path.cwd(),current,args.report)
    print({k:v for k,v in result.items() if k not in {'run_scopes','probes'}})


if __name__=='__main__':
    main()
