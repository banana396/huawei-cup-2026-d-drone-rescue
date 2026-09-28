# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""第四问分组、冻结架次、独立资源占用与组内通信复核。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from math import ceil,isclose
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources,make_leg
from diagnose_q3 import transport_phases
from radio import Position,direct,relay_path
from communication_schedule import solution_hash,schedule_hash
from certify_communication_boundaries import inspect as inspect_boundaries

ROOT=Path(__file__).resolve().parent


def peak(intervals):
    times=sorted({x for ab in intervals for x in ab})
    return max((sum(a<=t<b for a,b in intervals) for t in times),default=0)


def frozen_relay_issues(group,frozen):
    expected=set().union(*(frozen[mid] for mid in group['mission_ids']))
    actual=set(group['relay_ids'])
    return [] if actual==expected else [('frozen relay mismatch',sorted(expected-actual),sorted(actual-expected))]


def inspect_group(g,missions,relays,nodes,models,res,terrain,radio,step=5):
    issues=[]
    own=[m for m in missions if m['id'] in g['mission_ids']]
    rr=[r for r in relays if r['id'] in g['relay_ids']]
    need={}
    for mid in models:
        row=[m for m in own if m['model']==mid]
        need[f'{mid}_craft']=peak([(m['start_s'],m['return_s']) for m in row])
        need[f'{mid}_batteries']=peak([(m['start_s'],m['battery_recharged_s']) for m in row])
    need['relay_craft']=peak([(r['start_s'],r['return_s']+res.relay_models['R'].turnaround_s) for r in rr])
    need['relay_components']=peak([(r['start_s'],r['component_recharged_s']) for r in rr])
    if need!=g['resources']:issues.append(('resource mismatch',need,g['resources']))
    if set(g['zones'])!={z for m in own for z in m['route']}:
        issues.append(('zone/mission mismatch',g['zones']))
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    failures=[];blind=0
    for m in own:
        if any(z not in g['zones'] for z in m['route']):issues.append((m['id'],'cross-group transport'))
        for phase in transport_phases(m,nodes,models,legs):
            n=max(1,ceil((phase.t1-phase.t0)/step))
            for k in range(n+1):
                t=phase.t0+(phase.t1-phase.t0)*k/n;p=phase.at(t)
                if direct(p,nodes,terrain,radio,'exact')['available']:continue
                blind+=1
                if not any(r['ready_s']-1e-8<=t<=r['service_end_s']+1e-8 and
                           relay_path(p,Position(r['lon'],r['lat'],r['alt_m']),nodes,terrain,radio,'exact')['available']
                           for r in rr):
                    if len(failures)<10:failures.append((m['id'],round(t,3)))
    if failures:issues.append(('uncovered in group',failures))
    return issues,{'blind_samples':blind,'resources':need}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--solution',type=Path,default=ROOT/'结果'/'q3_solution.json')
    parser.add_argument('--q4',type=Path,default=ROOT/'结果'/'q4_results.json')
    parser.add_argument('--output',type=Path,default=ROOT/'结果'/'q4_check.json')
    parser.add_argument('--communication',type=Path,default=ROOT/'结果'/'q3_communication_schedule.json')
    parser.add_argument('--boundary-guards',type=Path,default=ROOT/'结果'/'q3_boundary_guards.json')
    args=parser.parse_args()
    q3=json.loads(args.solution.read_text(encoding='utf-8'))
    q4=json.loads(args.q4.read_text(encoding='utf-8'))
    communication=json.loads(args.communication.read_text(encoding='utf-8'))
    guards=json.loads(args.boundary_guards.read_text(encoding='utf-8'))
    communication_check=json.loads((ROOT/'结果'/'q3_communication_check.json').read_text(encoding='utf-8'))
    nodes,models,boxes=load_inputs();res=load_resources();terrain=Terrain();issues=[];summary={}
    if q4.get('q3_solution_sha256')!=solution_hash(q3) or communication['solution_sha256']!=solution_hash(q3):
        issues.append('stale Q3/communication source')
    if q4.get('communication_sha256')!=schedule_hash(communication):issues.append('stale frozen communication records')
    if communication_check['status']!='passed' or communication_check['communication_sha256']!=schedule_hash(communication):
        issues.append('missing matching continuous communication verification')
    if inspect_boundaries(q3,communication)!=guards:issues.append('boundary guarantees do not reproduce')
    frozen={m['id']:set() for m in q3['transport_missions']}
    for row in communication['records']:
        if row['mode']=='中继':frozen[row['mission']].add(row['relay_id'])
    if guards['communication_sha256']!=schedule_hash(communication):issues.append('stale boundary guards')
    for guard in guards['guards']:
        if guard['guaranteed_relay_id']:frozen[guard['mission']].add(guard['guaranteed_relay_id'])
    if {mid:set(ids) for mid,ids in q4['relay_dependence'].items()}!=frozen:
        issues.append('Q4 changed frozen Q3 communication dependence')
    all_zones={b.zone for b in boxes.values()};all_missions={m['id'] for m in q3['transport_missions']}
    for k,options in q4['solutions'].items():
        summary[k]={}
        for label in ('resource_priority','balanced_resource_priority','balance_priority'):
            sol=options[label];groups=sol['groups'];local=[]
            if len(groups)!=int(k):local.append('group count')
            if Counter(z for g in groups for z in g['zones'])!=Counter({z:1 for z in all_zones}):local.append('zone partition')
            if Counter(mid for g in groups for mid in g['mission_ids'])!=Counter({m:1 for m in all_missions}):local.append('mission partition')
            checks=[]
            for g in groups:
                local.extend(frozen_relay_issues(g,frozen))
                error,stat=inspect_group(g,q3['transport_missions'],q3['relay_sorties'],nodes,models,res,terrain,res.radio)
                local.extend(error);checks.append(stat)
            total={key:sum(g['resources'][key] for g in groups) for key in sol['inventory']}
            if total!=sol['total_required']:local.append('resource total')
            actual_inventory={f'{mid}_craft':sum(x==mid for x in res.transport_craft.values()) for mid in models}
            actual_inventory.update({f'{mid}_batteries':res.transport_batteries[mid][0] for mid in models})
            actual_inventory.update(relay_craft=len(res.relay_craft),relay_components=res.relay_components['R'][0])
            if sol['inventory']!=actual_inventory:local.append('inventory mismatch')
            short={key:max(0,total[key]-sol['inventory'][key]) for key in total}
            if short!=sol['shortfall']:local.append('shortfall')
            work=[sum(m['return_s']-m['start_s'] for m in q3['transport_missions'] if m['id'] in g['mission_ids']) for g in groups]
            imbalance=(max(work)-min(work))/sum(work)
            if not isclose(imbalance,sol['work_imbalance_ratio'],abs_tol=1e-9):local.append('imbalance')
            summary[k][label]={'issues':local,'groups':checks}
            print(k,label,'issues',len(local),'group_blind_samples',[x['blind_samples'] for x in checks])
            issues.extend((k,label,x) for x in local)
    path=args.output
    altered=json.loads(json.dumps(q4['solutions']['2']['balanced_resource_priority']['groups'][0]))
    altered['relay_ids'].pop()
    injection_detected=bool(frozen_relay_issues(altered,frozen))
    if not injection_detected:issues.append('failed to detect deleted frozen relay')
    path.write_text(json.dumps({'status':'passed_sampled_verification' if not issues else 'failed',
                                'step_s':5,'summary':summary,'issues':issues,
                                'frozen_relation_check':'exact equality including numerical boundary guards',
                                'continuous_coverage':'inherited verified Q3 paths retained in each group',
                                'communication_sha256':schedule_hash(communication),
                                'injected_deleted_relay_detected':injection_detected},ensure_ascii=False,indent=2),encoding='utf-8')
    for issue in issues[:20]:print(issue)
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
