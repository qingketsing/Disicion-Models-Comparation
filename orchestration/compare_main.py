"""Compare completed Qwen/Jev main repeats on identical, ordered frozen inputs."""

import argparse
import itertools
from collections import Counter
from pathlib import Path

from decisionbench.analysis import audit_run, paired_bootstrap, read_json, write_csv
from decisionbench.artifacts import file_hash, write_json
from decisionbench.datasets import load_catalog
from decisionbench.suite import completed_entry, verify_bundle


def matched_differences(left_samples, left_catalog, left_rows, right_samples, right_catalog, right_rows):
    left_inputs = [(s.sample_id, s.text, s.label) for s in left_samples]
    right_inputs = [(s.sample_id, s.text, s.label) for s in right_samples]
    if left_inputs != right_inputs:
        raise ValueError('main inputs differ in sample ID, order, text or ground truth')
    if (left_catalog.version, list(left_catalog.labels.items())) != (
        right_catalog.version, list(right_catalog.labels.items())
    ):
        raise ValueError('main catalog version, label order or descriptions differ')
    a = {r['sample_id']: r for r in left_rows}
    b = {r['sample_id']: r for r in right_rows}
    if len(a) != len(left_rows) or len(b) != len(right_rows) or a.keys() != b.keys():
        raise ValueError('main predictions contain duplicate or different sample IDs')
    differences, cases = [], []
    for sid, text, truth in left_inputs:
        if a[sid]['expected_label'] != truth or b[sid]['expected_label'] != truth:
            raise ValueError('prediction ground truth differs from dataset')
        ac = a[sid]['status']=='ok' and a[sid]['prediction']==truth
        bc = b[sid]['status']=='ok' and b[sid]['prediction']==truth
        outcome = ('both_correct' if ac and bc else 'qwen_only' if ac else
                   'jev_only' if bc else 'both_wrong')
        differences.append(int(bc)-int(ac))
        cases.append(dict(sample_id=sid, text=text, expected_label=truth, outcome=outcome,
                          qwen_prediction=a[sid]['prediction'], jev_prediction=b[sid]['prediction']))
    return differences, cases


def compare(qwen_report, jev_plan, root, out):
    if out.exists():
        raise ValueError('comparison directory exists; preserve prior analyses')
    spec = read_json(jev_plan)
    verify_bundle(spec, root)
    state = read_json(root/'results/suites'/file_hash(jev_plan)/'index.json')
    jev = []
    for job in sorted(spec['jobs'], key=lambda j: j['repeat']):
        if job['model'] != 'jev' or job['block'] != 'main':
            continue
        entry = state['jobs'].get(job['id'], {})
        if not completed_entry(entry, job, root):
            raise ValueError('Jev main repeat has not completed')
        jev.append(root/entry['run_dir'])
    qwen = sorted(root/r['run'] for r in read_json(qwen_report/'audit.json')['runs']
                  if '-main-' in r['run'] and '-qwen-' in r['run'])
    if len(jev)!=3 or len(qwen)!=3 or len(set(jev+qwen))!=6:
        raise ValueError('exactly three distinct main repeats per model are required')

    def load(directory, model):
        m, rows, samples, summary, quality, cost = audit_run(directory)
        if m['synthetic'] or m['config']['adapter']['kind'] != model:
            raise ValueError('only actual model main results enter this comparison')
        if model=='qwen' and m['config']['environment'].get('structured_outputs_backend')!='guidance':
            raise ValueError('comparison requires the sealed Qwen guidance v4 runs')
        for source,digest in m['source_files'].items():
            if file_hash(directory/'source'/source)!=digest:
                raise ValueError('main source snapshot differs')
        return dict(directory=directory, rows=rows, samples=samples,
                    catalog=load_catalog(directory/'inputs/catalog-0.json'), quality=quality,
                    requests_sha256=file_hash(directory/'requests.jsonl'),
                    manifest_sha256=file_hash(directory/'manifest.json'), cost=cost)

    left = [load(p,'qwen') for p in qwen]
    right = [load(p,'jev') for p in jev]
    comparisons, all_cases, disagreements = [], [], []
    for repeat,(a,b) in enumerate(zip(left,right),1):
        diffs,cases = matched_differences(a['samples'],a['catalog'],a['rows'],
                                         b['samples'],b['catalog'],b['rows'])
        mean,lo,hi = paired_bootstrap(diffs,seed=42,draws=2000)
        outcomes = Counter(c['outcome'] for c in cases)
        comparisons.append(dict(repeat=repeat, unique_samples=len(diffs),
                                qwen_accuracy=a['quality']['accuracy'],jev_accuracy=b['quality']['accuracy'],
                                accuracy_jev_minus_qwen=mean,ci95_low=lo,ci95_high=hi,
                                **{name: outcomes[name] for name in
                                   ('both_correct','qwen_only','jev_only','both_wrong')}))
        all_cases += [dict(repeat=repeat,**c) for c in cases]
        for peer in right:
            # All Jev repeats must also share the exact frozen sample/catalog semantics.
            matched_differences(a['samples'],a['catalog'],a['rows'],
                                peer['samples'],peer['catalog'],peer['rows'])
    for model,group in [('qwen',left),('jev',right)]:
        for i,j in itertools.combinations(range(3),2):
            maps=[{r['sample_id']:(r['status'],r['prediction']) for r in group[k]['rows']}
                  for k in (i,j)]
            disagreements.append(dict(model=model,repeat_a=i+1,repeat_b=j+1,
                                       unique_samples=len(maps[0]),
                                       prediction_differences=sum(maps[0][k]!=maps[1][k] for k in maps[0])))
    out.mkdir(parents=True)
    write_csv(out/'paired-comparisons.csv',comparisons)
    write_csv(out/'paired-sample-outcomes.csv',all_cases)
    write_csv(out/'repeat-disagreements.csv',disagreements)
    write_json(out/'audit.json',dict(
        jev_plan_sha256=file_hash(jev_plan),qwen_report_audit_sha256=file_hash(qwen_report/'audit.json'),
        unique_main_samples=len(left[0]['samples']),repeats_per_model=3,
        repeated_measurements_are_not_independent=True,
        input_comparison='Exact ordered sample ID/text/GT and ordered catalog labels/descriptions/version; newline bytes may differ.',
        bootstrap=dict(draws=2000,seed=42,unit='unique sample within each paired repeat'),
        comparisons=comparisons,repeat_disagreements=disagreements,
        runs=[dict(model=model,run=str(r['directory'].relative_to(root)),quality=r['quality'],
                   requests_sha256=r['requests_sha256'],manifest_sha256=r['manifest_sha256'])
              for model,group in [('qwen',left),('jev',right)] for r in group],
        limitation='Quality on this fixed dataset/catalog. Qwen remote GPU and Jev local Internet API '
        'use different deployment/network conditions and transport-retry policies; latency/cost are not controlled model-only comparisons.',
    ))
    return comparisons


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qwen-report',type=Path,required=True)
    parser.add_argument('--jev-plan',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(compare(args.qwen_report.resolve(),args.jev_plan.resolve(),Path.cwd(),args.out.resolve()))


if __name__=='__main__':
    main()
