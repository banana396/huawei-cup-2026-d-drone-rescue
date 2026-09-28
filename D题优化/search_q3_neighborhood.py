# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""Q3 运输邻域搜索。固定已验证的中继网络，改变组批、路线和拆分任务实体。

不覆盖正式结果。点值筛查仅用于淘汰候选；入选还须独立运输账检查和连续通信认证。
搜索范围明确受限：硬任务不动，未修改任务不动，已有任务起始时刻不动。
"""
from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import sys
from collections import Counter, defaultdict
from math import ceil, inf
from pathlib import Path

from check_q2 import inspect as inspect_transport
from check_q3 import inspect as inspect_joint
from d_common import Terrain, charging_time_s, load_inputs, load_resources, make_leg
from diagnose_q3 import transport_phases
from radio import Position, direct, gateway, link_budget
from solve_q2 import Task, hard_deadline, mission_profile

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '结果'


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = OUT / 'q3_solution.json'
    source_before = digest(source)
    data = json.loads(source.read_text(encoding='utf-8'))
    nodes, models, boxes = load_inputs()
    resources = load_resources()
    terrain = Terrain()
    legs = {(a, b): make_leg(terrain, nodes[a], nodes[b])
            for a in nodes for b in nodes if a != b}
    original = data['transport_missions']
    soft = [i for i, m in enumerate(original)
            if all(hard_deadline(boxes[b]) == inf for b in m['delivery_s'])]
    relays = data['relay_sorties']
    gate = gateway(nodes, resources.radio)
    relay_positions = {r['id']: Position(r['lon'], r['lat'], r['alt_m']) for r in relays}
    backhaul = {r['id']: link_budget(relay_positions[r['id']], gate, terrain, resources.radio,
                                    '中继回传端', '固定网关 G01', 'exact')['available'] for r in relays}
    counts = Counter()
    family_counts = defaultdict(Counter)
    rejected = defaultdict(list)
    seen = set()
    screened = []

    def task(m):
        return tuple((s['zone'], tuple(s['boxes'])) for s in m['stops'])

    def build(old, stops, model=None, craft=None, battery=None):
        if not stops:
            return None
        mid = model or old['model']
        p = mission_profile(Task(tuple(stops)), models[mid], boxes, legs)
        if p is None:
            return None
        start = old['start_s']
        end = start + p['duration']
        soc = 1 - p['energy'] / models[mid].energy_kwh
        return dict(id=old['id'], craft=craft or old['craft'], model=mid,
                    battery=battery or old['battery'], start_s=start,
                    route=[z for z, _ in stops],
                    stops=[{'zone': z, 'boxes': list(bs)} for z, bs in stops],
                    return_s=round(end, 6), energy_kwh=round(p['energy'], 9),
                    return_soc=round(soc, 9),
                    delivery_s={b: round(start + t, 6) for b, t in p['deliveries'].items()},
                    battery_recharged_s=round(end + charging_time_s(
                        soc, resources.transport_batteries[mid][1]), 6))

    def metrics(rows):
        delivery = {b: t for m in rows for b, t in m['delivery_s'].items()}
        return {'sorties': len(rows), 'relay_sorties': len(relays),
                'energy_kwh': sum(m['energy_kwh'] for m in rows),
                'total_energy_kwh': sum(m['energy_kwh'] for m in rows) + sum(r['energy_kwh'] for r in relays),
                'makespan_s': max(m['return_s'] for m in rows),
                'joint_makespan_s': max([m['return_s'] for m in rows] + [r['return_s'] for r in relays]),
                'weighted_lateness_s': sum(boxes[b].priority * max(0, t - boxes[b].expected_s)
                                           for b, t in delivery.items() if boxes[b].kind != '医疗物资')}

    def objective(m):
        return m['weighted_lateness_s'], m['joint_makespan_s'], m['total_energy_kwh'], m['sorties'] + m['relay_sorties']

    baseline = metrics(original)

    def conflicts(rows):
        for key, endkey in [('craft', 'return_s'), ('battery', 'battery_recharged_s')]:
            events = defaultdict(list)
            for m in rows:
                events[m[key]].append((m['start_s'], m[endkey]))
            for spans in events.values():
                spans.sort()
                if any(b[0] < a[1] - 1e-6 for a, b in zip(spans, spans[1:])):
                    return True
        return False

    comm_cache = {}

    def screen_communication(m):
        signature = json.dumps({k: m[k] for k in ('model', 'stops', 'start_s', 'return_s')}, sort_keys=True)
        if signature in comm_cache:
            return comm_cache[signature]
        for phase in transport_phases(m, nodes, models, legs):
            n = max(1, ceil((phase.t1 - phase.t0) / 8))
            times = {phase.t0 + (phase.t1 - phase.t0) * k / n for k in range(n + 1)}
            for r in relays:
                for t in (r['ready_s'], r['service_end_s']):
                    if phase.t0 <= t <= phase.t1:
                        times.add(t)
            for t in sorted(times):
                p = phase.at(t)
                if direct(p, nodes, terrain, resources.radio, 'exact')['available']:
                    continue
                if not any(backhaul[r['id']] and r['ready_s'] <= t <= r['service_end_s']
                           and link_budget(p, relay_positions[r['id']], terrain, resources.radio,
                                           '运输无人机', '中继接入端', 'exact')['available'] for r in relays):
                    comm_cache[signature] = (False, (m['id'], phase.kind, t))
                    return comm_cache[signature]
        comm_cache[signature] = (True, None)
        return comm_cache[signature]

    def consider(label, replaced, added=()):
        counts['generated'] += 1
        family = label.split(':')[0]
        family_counts[family]['generated'] += 1
        # None intentionally removes an emptied donor mission.
        rows = [replaced.get(i, m) for i, m in enumerate(original)] + list(added)
        rows = [m for m in rows if m is not None]
        signature = json.dumps(rows, sort_keys=True)
        if signature in seen:
            counts['duplicate'] += 1
            return
        seen.add(signature)
        actual = Counter(b for m in rows for s in m['stops'] for b in s['boxes'])
        if actual != Counter({b: 1 for b in boxes}):
            raise AssertionError(('neighborhood lost/duplicated box', label))
        if conflicts(rows):
            counts['resource_conflict'] += 1
            return
        m = metrics(rows)
        if objective(m) >= objective(baseline):
            counts['not_improved'] += 1
            return
        counts['improving_resource_feasible'] += 1
        changed = [r for r in replaced.values() if r] + list(added)
        for r in changed:
            ok, witness = screen_communication(r)
            if not ok:
                counts['communication_rejected'] += 1
                if len(rejected[label.split(':')[0]]) < 5:
                    rejected[label.split(':')[0]].append(witness)
                return
        issues = inspect_transport(rows, m, nodes, models, boxes, resources, terrain)
        if issues:
            raise AssertionError(('candidate construction mismatch', label, issues))
        counts['screened_feasible'] += 1
        family_counts[family]['screened_feasible'] += 1
        is_best = not screened or objective(m) < min(x[0] for x in screened)
        screened.append((objective(m), label, rows, m))
        if is_best:
            print('new screened best', label, objective(m), flush=True)

    for i in soft:
        a = task(original[i])
        for perm in itertools.permutations(a):
            if perm != a and (new := build(original[i], perm)) is not None:
                consider(f'route:{original[i]["id"]}', {i: new})
        for j in soft:
            if i == j:
                continue
            b = task(original[j])
            for k, stop in enumerate(a):
                reduced = a[:k] + a[k + 1:]
                donor = build(original[i], reduced)
                if reduced and donor is None:
                    continue
                # Move an entire stop; consolidate an already present service zone.
                if stop[0] in [z for z, _ in b]:
                    orders = [tuple((z, ids + stop[1] if z == stop[0] else ids) for z, ids in b)]
                else:
                    orders = [b[:at] + (stop,) + b[at:] for at in range(len(b) + 1)]
                for order in orders:
                    if (receiver := build(original[j], order)) is not None:
                        consider(f'relocate:{original[i]["id"]}->{original[j]["id"]}:{stop[0]}',
                                 {i: donor, j: receiver})
                # Individual indivisible boxes can be rebalanced between same-zone stops.
                if stop[0] in [z for z, _ in b] and len(stop[1]) > 1:
                    for box in stop[1]:
                        aa = tuple((z, tuple(x for x in ids if x != box)) for z, ids in a)
                        bb = tuple((z, ids + (box,) if z == stop[0] else ids) for z, ids in b)
                        donor, receiver = build(original[i], aa), build(original[j], bb)
                        if donor is not None and receiver is not None:
                            consider(f'box:{box}:{i}->{j}', {i: donor, j: receiver})
        if len(a) > 1:
            for k, stop in enumerate(a):
                donor = build(original[i], a[:k] + a[k + 1:])
                if donor is None:
                    continue
                for mid in models:
                    for uid, craft_mid in resources.transport_craft.items():
                        if craft_mid != mid:
                            continue
                        for bi in range(1, resources.transport_batteries[mid][0] + 1):
                            seed = dict(original[i], id='Q3-027')
                            extra = build(seed, (stop,), mid, uid, f'{mid}-BAT-{bi:02d}')
                            if extra is not None:
                                consider(f'split:{original[i]["id"]}:{stop[0]}:{uid}:{bi}', {i: donor}, [extra])

    # Full continuous certification in declared objective order; stop at the first pass.
    trials = []
    accepted = None
    for rank, (_, label, rows, m) in enumerate(sorted(screened, key=lambda x: (x[0], x[1])), 1):
        candidate = dict(data)
        candidate.update(status='candidate_pending_continuous_verification', transport_missions=rows,
                         mission_relays={}, search_metadata={'operation': label,
                         'source_sha256': digest(source), 'scope': 'fixed relay network; one transportation neighborhood move'})
        path = OUT / f'q3_joint_candidate_{rank:03d}.json'
        dump(path, candidate)
        run = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'certify_q3_intervals.py'),
                              '--solution', str(path)], capture_output=True, text=True, encoding='utf-8')
        cert = OUT / f'q3_interval_certificate_{path.stem}.json'
        trial = {'rank': rank, 'operation': label, 'candidate': path.name,
                 'candidate_sha256': digest(path), 'metrics': m, 'certificate_exit_code': run.returncode}
        if cert.exists():
            trial['certificate'] = cert.name
            trial['certificate_sha256'] = digest(cert)
        else:
            trial['error'] = run.stderr[-2000:]
        trials.append(trial)
        print('continuous trial', rank, run.returncode, label, flush=True)
        if run.returncode == 0:
            issues, checked_metrics = inspect_joint(candidate, step_s=2, step_pixels='exact')
            trial['physical_check_issues'] = issues
            trial['physical_check_metrics'] = checked_metrics
            if issues:
                raise AssertionError(('continuous candidate physical checks failed', issues))
            accepted = trial
            break

    assert digest(source) == source_before, 'Official Q3 changed during search'
    report = {'status': 'improvement_certified_pending_full_pipeline' if accepted else 'no_certified_improvement',
              'source_sha256': digest(source), 'script_sha256': digest(Path(__file__)),
              'scope': 'One-move soft-task neighborhood; fixed hard tasks, existing mission starts and relay sorties; not global or local optimality proof',
              'objective_order': ['weighted_lateness_s', 'joint_makespan_s', 'total_energy_kwh', 'total_sorties'],
              'baseline': baseline, 'counts': counts, 'operation_counts': family_counts,
              'screened_candidates': [{'operation': label, 'metrics': m} for _, label, _, m in screened],
              'communication_rejection_witnesses': rejected,
              'trials': trials, 'accepted': accepted,
              'formal_solution_overwritten': False,
              'remaining_gate': 'Regenerate communication records/boundaries, Q4, six tables, figures, report, full reproduction before promoting'}
    dump(OUT / 'q3_neighborhood_search.json', report)
    print('search result', report['status'], counts, flush=True)


if __name__ == '__main__':
    main()
