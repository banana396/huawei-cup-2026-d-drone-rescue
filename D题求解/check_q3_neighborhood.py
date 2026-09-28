# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""核验邻域对照来源、约束、名义证书与额外裕量失败的结论，含故障注入。"""
import copy
import hashlib
import json
from math import isclose
from pathlib import Path

from check_q3 import inspect
from d_common import load_inputs
from solve_q2 import hard_deadline

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '结果'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_metadata(report, candidate, nominal, stress):
    issues = []
    official = read(OUT / 'q3_solution.json')
    accepted = report['accepted']
    path = OUT / accepted['candidate']
    if report['source_sha256'] != digest(OUT / 'q3_solution.json'):
        issues.append('stale official source')
    if report['script_sha256'] != digest(ROOT / 'search_q3_neighborhood.py'):
        issues.append('stale search script')
    if accepted['candidate_sha256'] != digest(path):
        issues.append('candidate hash')
    if not nominal['certified_all_intervals'] or nominal['source_sha256'] != digest(path):
        issues.append('nominal certificate')
    if stress['source_sha256'] != digest(path) or stress['required_margin_db'] != 1:
        issues.append('stress certificate source')
    if stress['certified_all_intervals'] or stress['counts'].get('point_counterexamples', 0) <= 0:
        issues.append('stress failure evidence missing')
    if candidate['relay_sorties'] != official['relay_sorties']:
        issues.append('relay network changed')
    _, _, boxes = load_inputs()
    rows = candidate['transport_missions']
    old = official['transport_missions']
    by_id = {r['id']: r for r in rows}
    for r in old:
        if any(hard_deadline(boxes[b]) < float('inf') for b in r['delivery_s']):
            if by_id.get(r['id']) != r:
                issues.append('hard mission changed')
    delivery = {b: t for r in rows for b, t in r['delivery_s'].items()}
    values = {
        'sorties': len(rows), 'relay_sorties': len(candidate['relay_sorties']),
        'energy_kwh': sum(r['energy_kwh'] for r in rows),
        'total_energy_kwh': sum(r['energy_kwh'] for r in rows + candidate['relay_sorties']),
        'makespan_s': max(r['return_s'] for r in rows),
        'joint_makespan_s': max(r['return_s'] for r in rows + candidate['relay_sorties']),
        'weighted_lateness_s': sum(boxes[b].priority * max(0, t - boxes[b].expected_s)
                                   for b, t in delivery.items() if boxes[b].kind != '医疗物资')}
    for key, value in values.items():
        if not isclose(value, accepted['metrics'][key], rel_tol=0, abs_tol=1e-7):
            issues.append('metric:' + key)
    baseline = report['baseline']
    old_delivery = {b: t for r in old for b, t in r['delivery_s'].items()}
    old_values = {
        'sorties': len(old), 'relay_sorties': len(official['relay_sorties']),
        'energy_kwh': sum(r['energy_kwh'] for r in old),
        'total_energy_kwh': sum(r['energy_kwh'] for r in old + official['relay_sorties']),
        'makespan_s': max(r['return_s'] for r in old),
        'joint_makespan_s': max(r['return_s'] for r in old + official['relay_sorties']),
        'weighted_lateness_s': sum(boxes[b].priority * max(0, t - boxes[b].expected_s)
                                   for b, t in old_delivery.items() if boxes[b].kind != '医疗物资')}
    for key, value in old_values.items():
        if not isclose(value, baseline[key], rel_tol=0, abs_tol=1e-7):
            issues.append('baseline metric:' + key)
    # This is a tradeoff, not Pareto domination: lateness improves but energy and sorties worsen.
    if not (values['weighted_lateness_s'] < baseline['weighted_lateness_s']
            and values['total_energy_kwh'] > baseline['total_energy_kwh']
            and values['sorties'] > baseline['sorties']):
        issues.append('tradeoff statement invalid')
    if sum(x['generated'] for x in report['operation_counts'].values()) != report['counts']['generated']:
        issues.append('candidate count')
    if len(report['screened_candidates']) != report['counts']['screened_feasible']:
        issues.append('screened candidate count')
    return issues


def main():
    report = read(OUT / 'q3_neighborhood_search.json')
    accepted = report['accepted']
    path = OUT / accepted['candidate']
    candidate = read(path)
    nominal_path = OUT / accepted['certificate']
    stress_path = OUT / f'q3_margin_certificate_1db_{path.stem}.json'
    nominal, stress = read(nominal_path), read(stress_path)
    issues = verify_metadata(report, candidate, nominal, stress)
    physical_issues, metrics = inspect(candidate, step_s=2, step_pixels='exact')
    issues.extend(physical_issues)
    faults = {}
    changed = copy.deepcopy(report)
    changed['source_sha256'] = '0' * 64
    faults['stale_source_detected'] = 'stale official source' in verify_metadata(changed, candidate, nominal, stress)
    changed = copy.deepcopy(report)
    changed['accepted']['metrics']['weighted_lateness_s'] -= 1000
    faults['false_metric_detected'] = 'metric:weighted_lateness_s' in verify_metadata(changed, candidate, nominal, stress)
    changed = copy.deepcopy(nominal)
    changed['certified_all_intervals'] = False
    faults['failed_certificate_detected'] = 'nominal certificate' in verify_metadata(report, candidate, changed, stress)
    if not all(faults.values()):
        issues.append('fault injection failed')
    out = {'status': 'passed' if not issues else 'failed', 'issues': issues,
           'physical_metrics': metrics, 'fault_injection': faults,
           'scope': 'Nominal feasible transportation-neighborhood tradeoff; not selected formal solution; 1 dB robustness failed',
           'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in
                             (OUT / 'q3_neighborhood_search.json', path, nominal_path, stress_path,
                              OUT / 'q3_solution.json', ROOT / 'search_q3_neighborhood.py')}}
    (OUT / 'q3_neighborhood_check.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(out['status'], 'issues', issues, 'faults', faults)
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
