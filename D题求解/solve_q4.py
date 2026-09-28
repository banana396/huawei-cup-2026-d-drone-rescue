# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""冻结Q3任务时序后枚举2/3组分区，核算独立执行的最少实体资源。"""
from __future__ import annotations

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path

from d_common import Terrain, load_inputs, load_resources, make_leg
from diagnose_q3 import transport_phases
from radio import Position, direct, relay_path
from communication_schedule import solution_hash,schedule_hash

ROOT=Path(__file__).resolve().parent


def peak(events):
    markers=[]
    for a,b in events:
        markers.extend([(a,1),(b,-1)])
    running=maximum=0
    for _,delta in sorted(markers):
        running+=delta
        maximum=max(maximum,running)
    return maximum


def relay_dependence(q3,communication,guards):
    """只读取已冻结的通信记录，禁止在第四问删除或替换保障中继。"""
    if communication['solution_sha256']!=solution_hash(q3):
        raise ValueError('通信记录与当前Q3不一致，请先重新生成并检查')
    result={m['id']:set() for m in q3['transport_missions']}
    for row in communication['records']:
        if row['mode']=='中继':result[row['mission']].add(row['relay_id'])
    if guards['communication_sha256']!=schedule_hash(communication):raise ValueError('边界保障版本不一致')
    for guard in guards['guards']:
        if guard['guaranteed_relay_id']:result[guard['mission']].add(guard['guaranteed_relay_id'])
    return {mid:sorted(ids) for mid,ids in result.items()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--solution',type=Path,default=ROOT/'结果'/'q3_solution.json')
    parser.add_argument('--output',type=Path,default=ROOT/'结果'/'q4_results.json')
    parser.add_argument('--communication',type=Path,default=ROOT/'结果'/'q3_communication_schedule.json')
    parser.add_argument('--boundary-guards',type=Path,default=ROOT/'结果'/'q3_boundary_guards.json')
    args=parser.parse_args()
    nodes,models,boxes=load_inputs();resources=load_resources();terrain=Terrain()
    q3=json.loads(args.solution.read_text(encoding='utf-8'))
    missions=q3['transport_missions'];relays=q3['relay_sorties']
    communication=json.loads(args.communication.read_text(encoding='utf-8'))
    guards=json.loads(args.boundary_guards.read_text(encoding='utf-8'))
    dependence=relay_dependence(q3,communication,guards)
    zones=sorted({b.zone for b in boxes.values()})
    parent={z:z for z in zones}
    def find(z):
        while z!=parent[z]:z=parent[z]
        return z
    for m in missions:
        for z in m['route'][1:]:
            parent[find(z)]=find(m['route'][0])
    comps=defaultdict(list)
    for z in zones:comps[find(z)].append(z)
    components=sorted((tuple(v) for v in comps.values()),key=lambda v:v[0])
    zone_to_index={z:i for i,comp in enumerate(components) for z in comp}
    mission_comp={m['id']:zone_to_index[m['route'][0]] for m in missions}
    comp_kg=[sum(b.kg for b in boxes.values() if b.zone in comp) for comp in components]
    comp_work=[sum(m['return_s']-m['start_s'] for m in missions if mission_comp[m['id']]==i)
               for i in range(len(components))]
    relay_by_id={r['id']:r for r in relays}
    cache={}

    def resources_for(mask):
        if mask in cache:return cache[mask]
        selected=[m for m in missions if mask&(1<<mission_comp[m['id']])]
        relay_ids={rid for m in selected for rid in dependence[m['id']]}
        selected_relays=[relay_by_id[rid] for rid in sorted(relay_ids)]
        need={}
        for model in models:
            work=[m for m in selected if m['model']==model]
            need[f'{model}_craft']=peak((m['start_s'],m['return_s']) for m in work)
            need[f'{model}_batteries']=peak((m['start_s'],m['battery_recharged_s']) for m in work)
        need['relay_craft']=peak((r['start_s'],r['return_s']+resources.relay_models['R'].turnaround_s)
                                 for r in selected_relays)
        need['relay_components']=peak((r['start_s'],r['component_recharged_s']) for r in selected_relays)
        out={'zones':[z for i,comp in enumerate(components) if mask&(1<<i) for z in comp],
             'mission_ids':[m['id'] for m in selected], 'relay_ids':sorted(relay_ids),
             'resources':need,'kg':sum(comp_kg[i] for i in range(len(components)) if mask&(1<<i)),
             'work_s':sum(comp_work[i] for i in range(len(components)) if mask&(1<<i)),
             'transport_sorties':len(selected),'relay_sorties':len(selected_relays)}
        cache[mask]=out
        return out

    inventory={f'{m}_craft':sum(v==m for v in resources.transport_craft.values()) for m in models}
    inventory.update({f'{m}_batteries':resources.transport_batteries[m][0] for m in models})
    inventory.update(relay_craft=len(resources.relay_craft),
                     relay_components=resources.relay_components['R'][0])

    def evaluate(masks):
        groups=[resources_for(mask) for mask in masks]
        total={k:sum(g['resources'][k] for g in groups) for k in inventory}
        short={k:max(0,total[k]-inventory[k]) for k in inventory}
        work=[g['work_s'] for g in groups]
        return {'groups':groups,'total_required':total,'inventory':inventory,'shortfall':short,
                'shortfall_units':sum(short.values()),'total_resource_units':sum(total.values()),
                'work_imbalance_ratio':(max(work)-min(work))/sum(work),
                'replicated_relay_sorties':sum(g['relay_sorties'] for g in groups)-len(relays)}

    answers={}
    for k in (2,3):
        best_resource=None;best_balance=None;best_balanced_resource=None;n=0
        # 首个连通分量固定在第1组，以除去标签置换。
        for assign_tail in itertools.product(range(k),repeat=len(components)-1):
            assign=(0,)+assign_tail
            if set(assign)!=set(range(k)):continue
            masks=[sum(1<<i for i,a in enumerate(assign) if a==g) for g in range(k)]
            result=evaluate(masks);n+=1
            resource_key=(result['shortfall_units'],result['total_resource_units'],result['work_imbalance_ratio'])
            balance_key=(result['work_imbalance_ratio'],result['shortfall_units'],result['total_resource_units'])
            if best_resource is None or resource_key<best_resource[0]:best_resource=(resource_key,result)
            if best_balance is None or balance_key<best_balance[0]:best_balance=(balance_key,result)
            if result['work_imbalance_ratio']<=.20 and (best_balanced_resource is None or resource_key<best_balanced_resource[0]):
                best_balanced_resource=(resource_key,result)
        answers[str(k)]={'partitions_evaluated':n,'resource_priority':best_resource[1],
                         'balance_priority':best_balance[1],
                         'balanced_resource_priority':best_balanced_resource[1] if best_balanced_resource else None}
        print('K',k,'partitions',n)
        for label in ('resource_priority','balanced_resource_priority','balance_priority'):
            x=answers[str(k)][label]
            print(label,'short',x['shortfall_units'],'required',x['total_required'],
                  'imbalance',round(x['work_imbalance_ratio'],4),'groups',[g['zones'] for g in x['groups']])
    out={'note':'冻结Q3的架次、时序与通信保障；跨组需要同一中继架次时在组内复制同时间任务，独立核算，不允许共享实体',
         'q3_solution_sha256':solution_hash(q3),
         'communication_sha256':schedule_hash(communication),
         'connected_components':components,'relay_dependence':dependence,'solutions':answers}
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
