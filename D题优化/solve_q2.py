# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""第二问可行调度基线。AI辅助编写；正式提交前按竞赛规定补全工具信息。"""
from __future__ import annotations

import itertools
import json
from collections import defaultdict
from dataclasses import dataclass
from math import inf
from pathlib import Path

from d_common import Terrain, charging_time_s, leg_energy, leg_time, load_inputs, load_resources, make_leg
from solve_q1 import solve_zone


OUT=Path(__file__).resolve().parent/'结果'


@dataclass(frozen=True)
class Task:
    stops: tuple[tuple[str,tuple[str,...]], ...]

    @property
    def boxes(self): return tuple(i for _,ids in self.stops for i in ids)


def hard_deadline(box):
    dates=[]
    if box.kind=='医疗物资': dates.append(box.expected_s)
    if box.first: dates.append(box.first_deadline_s)
    return min(dates) if dates else inf


def mission_profile(task, model, boxes, legs):
    selected=[boxes[i] for i in task.boxes]
    kg=sum(b.kg for b in selected)
    m3=sum(b.m3 for b in selected)
    if kg>model.max_kg+1e-9 or m3>model.max_m3+1e-9: return None
    elapsed=model.prep_s+len(selected)*model.load_box_s
    energy=0.; remaining=kg; last='O01'; deliveries={}; legs_out=[]
    for zone,ids in task.stops:
        leg=legs[last,zone]
        energy+=leg_energy(model,leg,remaining)
        elapsed+=leg_time(model,leg)
        handoff=model.handoff_base_s+len(ids)*model.handoff_box_s
        elapsed+=handoff
        for i in ids: deliveries[i]=elapsed
        remaining-=sum(boxes[i].kg for i in ids)
        legs_out.append((last,zone,remaining,round(elapsed,6)))
        last=zone
    back=legs[last,'O01']
    energy+=leg_energy(model,back,0.)
    elapsed+=leg_time(model,back)
    if energy>(1-model.reserve)*model.energy_kwh+1e-9: return None
    if any(t>hard_deadline(boxes[i])+1e-9 for i,t in deliveries.items() if hard_deadline(boxes[i])<inf):
        # 单架次从 t=0 起都来不及，不可能靠排班修正。
        return None
    return {'energy':energy,'duration':elapsed,'deliveries':deliveries,'legs':legs_out,'kg':kg,'m3':m3}


def best_energy(task, models, boxes, legs):
    pairs=[(p['energy'],m.id,p) for m in models.values() if (p:=mission_profile(task,m,boxes,legs)) is not None]
    return min(pairs) if pairs else None


def build_tasks(boxes, models, legs):
    by_zone=defaultdict(list)
    for b in boxes.values(): by_zone[b.zone].append(b)
    tasks=[]
    for zone,items in sorted(by_zone.items()):
        urgent=[b for b in items if hard_deadline(b)<inf]
        rest=[b for b in items if hard_deadline(b)==inf]
        if urgent: tasks.append(Task(((zone,tuple(b.id for b in urgent)),)))
        if rest:
            trips=solve_zone(zone,rest,models,legs['O01',zone],legs[zone,'O01'],.20)
            if trips is None: raise RuntimeError(f'剩余货箱无法组批: {zone}')
            tasks.extend(Task(((zone,tuple(t['boxes'])),)) for t in trips)
    return tasks


def merge_soft_tasks(tasks, models, boxes, legs):
    # 仅合并无硬时限的任务，最多3站，保留不少于3个跨区连通分量供问题四研究。
    hard=[t for t in tasks if any(hard_deadline(boxes[i])<inf for i in t.boxes)]
    soft=[t for t in tasks if t not in hard]
    merged_count=0
    while len(soft)>3:
        best=None
        for i in range(len(soft)):
            for j in range(i+1,len(soft)):
                a,b=soft[i],soft[j]
                zones={z for z,_ in a.stops+b.stops}
                if len(zones)<2 or len(zones)>3: continue
                pa=best_energy(a,models,boxes,legs)
                pb=best_energy(b,models,boxes,legs)
                if pa is None or pb is None: continue
                for ordered in itertools.permutations(a.stops+b.stops):
                    task=Task(ordered)
                    pc=best_energy(task,models,boxes,legs)
                    if pc is None: continue
                    savings=pa[0]+pb[0]-pc[0]
                    if savings<=.005: continue
                    if best is None or savings>best[0]: best=(savings,i,j,task)
        if best is None: break
        _,i,j,new=best
        soft=[t for k,t in enumerate(soft) if k not in (i,j)]+[new]
        merged_count+=1
    return hard+soft,merged_count


def schedule(tasks, nodes, models, boxes, resources, legs, task_order=None, selection='delivery', profile_cache=None):
    craft_available={u:0. for u in resources.transport_craft}
    batteries={m:[{'id':f'{m}-BAT-{i:02d}','available':0.} for i in range(1,resources.transport_batteries[m][0]+1)] for m in models}
    def priority(t):
        due=min(hard_deadline(boxes[i]) for i in t.boxes)
        far=max(legs['O01',z].distance_m for z,_ in t.stops)
        return (due,-far,-len(t.boxes))
    records=[]
    for task in (sorted(tasks,key=priority) if task_order is None else task_order):
        choice=None; nearest_late=None
        for uid,mid in resources.transport_craft.items():
            m=models[mid]
            cache_key=(task,mid)
            if profile_cache is not None and cache_key in profile_cache:p=profile_cache[cache_key]
            else:
                p=mission_profile(task,m,boxes,legs)
                if profile_cache is not None:profile_cache[cache_key]=p
            if p is None: continue
            for battery in batteries[mid]:
                start=max(craft_available[uid],battery['available'])
                violations=[(i,start+dt-hard_deadline(boxes[i])) for i,dt in p['deliveries'].items() if start+dt>hard_deadline(boxes[i])+1e-8]
                if violations:
                    late=max(x[1] for x in violations)
                    if nearest_late is None or late<nearest_late[0]: nearest_late=(late,task,uid,start)
                    continue
                # 先最小化本任务的交付/返回时刻，再以能量打破平局。
                key=(max(start+dt for dt in p['deliveries'].values()),start+p['duration'],p['energy'],uid,battery['id'])
                if selection=='lateness':
                    late=sum(boxes[i].priority*max(0,start+dt-boxes[i].expected_s)
                             for i,dt in p['deliveries'].items() if boxes[i].kind!='医疗物资')
                    key=(late,max(max(craft_available.values()),start+p['duration']),*key)
                elif selection=='energy':key=(p['energy'],*key)
                if choice is None or key<choice[0]: choice=(key,task,uid,battery,p,start)
        if choice is None:
            raise RuntimeError(f'找不到满足硬约束的分配: {task}; 最近迟到={nearest_late}')
        _,task,uid,battery,p,start=choice
        mid=resources.transport_craft[uid]
        end=start+p['duration']; soc=1-p['energy']/models[mid].energy_kwh
        record={'id':f'Q2-{len(records)+1:03d}','craft':uid,'model':mid,'battery':battery['id'],
                'start_s':round(start,6),'route':[z for z,_ in task.stops],
                'stops':[{'zone':z,'boxes':list(ids)} for z,ids in task.stops],
                'return_s':round(end,6),'energy_kwh':round(p['energy'],9),'return_soc':round(soc,9),
                'delivery_s':{i:round(start+dt,6) for i,dt in p['deliveries'].items()},
                'battery_recharged_s':round(end+charging_time_s(soc,resources.transport_batteries[mid][1]),6)}
        records.append(record)
        craft_available[uid]=end
        battery['available']=record['battery_recharged_s']
    return records


def main():
    nodes,models,boxes=load_inputs()
    resources=load_resources(); terrain=Terrain()
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    tasks=build_tasks(boxes,models,legs)
    baseline=schedule(tasks,nodes,models,boxes,resources,legs)
    merged,merge_count=merge_soft_tasks(tasks,models,boxes,legs)
    try: improved=schedule(merged,nodes,models,boxes,resources,legs)
    except RuntimeError as err:
        print('合并方案未通过排班，沿用基线:',err)
        improved=baseline; merge_count=0
    def metrics(rows):
        delivery={i:t for r in rows for i,t in r['delivery_s'].items()}
        return {'sorties':len(rows),'energy_kwh':round(sum(r['energy_kwh'] for r in rows),6),
                'makespan_s':round(max(r['return_s'] for r in rows),6),
                'weighted_lateness_s':round(sum(boxes[i].priority*max(0,t-boxes[i].expected_s) for i,t in delivery.items() if boxes[i].kind!='医疗物资'),6),
                'medical_late':sum(t>boxes[i].expected_s+1e-8 for i,t in delivery.items() if boxes[i].kind=='医疗物资'),
                'first_late':sum(t>boxes[i].first_deadline_s+1e-8 for i,t in delivery.items() if boxes[i].first)}
    result={'assumptions':{'start_time':'工位准备开始时刻；装载、飞行、逐站交接均计入。',
                           'delivery_time':'该站全部所载货箱完成基础交接和逐箱交接后的时刻；同站同架次保守记同一完成时刻。',
                           'battery':'自架次开始至返航占用，返航后按题面两阶段模型充满才可复用；各电池并行充电。',
                           'scope':'Q2暂不考虑通信；医疗期望与首批截止均为硬约束。'},
            'baseline':{'metrics':metrics(baseline),'missions':baseline},
            'merged':{'merge_operations':merge_count,'metrics':metrics(improved),'missions':improved}}
    OUT.mkdir(exist_ok=True)
    path=OUT/'q2_results.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(path)
    print('baseline',result['baseline']['metrics'])
    print('merged',result['merged']['metrics'],'merge_operations',merge_count)


if __name__=='__main__': main()
