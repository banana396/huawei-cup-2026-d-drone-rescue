# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""第二问独立结果检查。读取已保存的方案，逐段重算，不调用求解器。"""
from __future__ import annotations

import json
import hashlib
from collections import Counter,defaultdict
from math import isclose
from pathlib import Path

from d_common import G,Terrain,charging_time_s,load_inputs,load_resources,make_leg


SOURCE=Path(__file__).resolve().parent/'结果'/'q2_results.json'


def inspect(rows, metrics, nodes, models, boxes, resources, terrain):
    issues=[]; seen=Counter(); by_craft=defaultdict(list); by_battery=defaultdict(list)
    valid_batteries={mid:{f'{mid}-BAT-{i:02d}' for i in range(1,resources.transport_batteries[mid][0]+1)} for mid in models}
    all_delivery={}
    for r in rows:
        name=r['id']; uid=r['craft']; mid=r['model']; bid=r['battery']
        if uid not in resources.transport_craft or resources.transport_craft.get(uid)!=mid:
            issues.append((name,'invalid craft/model')); continue
        if bid not in valid_batteries[mid]: issues.append((name,'invalid battery')); continue
        m=models[mid]; start=r['start_s']; end=r['return_s']
        if start<0 or end<=start: issues.append((name,'invalid time'))
        stops=r['stops']
        if not stops or [x['zone'] for x in stops]!=r['route']:
            issues.append((name,'route/stops mismatch')); continue
        box_ids=[i for stop in stops for i in stop['boxes']]
        if not box_ids or len(set(box_ids))!=len(box_ids) or any(i not in boxes for i in box_ids):
            issues.append((name,'empty, duplicate or unknown boxes')); continue
        for stop in stops:
            if stop['zone'] not in nodes or any(boxes[i].zone!=stop['zone'] for i in stop['boxes']):
                issues.append((name,'box/zone mismatch'))
        for i in box_ids: seen[i]+=1
        kg=sum(boxes[i].kg for i in box_ids); m3=sum(boxes[i].m3 for i in box_ids)
        if kg>m.max_kg+1e-9 or m3>m.max_m3+1e-9: issues.append((name,'capacity'))
        elapsed=m.prep_s+len(box_ids)*m.load_box_s
        energy=0.; current=kg; prev='O01'; deliveries={}
        for stop in stops:
            z=stop['zone']; leg=make_leg(terrain,nodes[prev],nodes[z])
            eq_range=m.range_empty_m-(m.range_empty_m-m.range_full_m)*(current/m.max_kg)**1.5
            energy+=m.energy_kwh*leg.distance_m/eq_range+(m.empty_kg+current)*G*leg.climb_m/(3_600_000*m.climb_eta)
            elapsed+=leg.climb_m/m.climb_mps+leg.distance_m/m.cruise_mps+leg.descent_m/m.descent_mps
            elapsed+=m.handoff_base_s+len(stop['boxes'])*m.handoff_box_s
            for i in stop['boxes']: deliveries[i]=start+elapsed
            current-=sum(boxes[i].kg for i in stop['boxes'])
            prev=z
        leg=make_leg(terrain,nodes[prev],nodes['O01'])
        energy+=m.energy_kwh*leg.distance_m/m.range_empty_m+m.empty_kg*G*leg.climb_m/(3_600_000*m.climb_eta)
        elapsed+=leg.climb_m/m.climb_mps+leg.distance_m/m.cruise_mps+leg.descent_m/m.descent_mps
        soc=1-energy/m.energy_kwh
        if soc<m.reserve-1e-9: issues.append((name,'reserve'))
        if not isclose(start+elapsed,end,abs_tol=3e-6): issues.append((name,'return time mismatch'))
        if not isclose(energy,r['energy_kwh'],abs_tol=3e-6): issues.append((name,'energy mismatch'))
        if not isclose(soc,r['return_soc'],abs_tol=3e-6): issues.append((name,'SOC mismatch'))
        if set(deliveries)!=set(r['delivery_s']): issues.append((name,'delivery list mismatch'))
        for i,t in deliveries.items():
            all_delivery[i]=t
            if not isclose(t,r['delivery_s'].get(i,-1),abs_tol=3e-6): issues.append((name,i,'delivery time mismatch'))
            if boxes[i].kind=='医疗物资' and t>boxes[i].expected_s+1e-8: issues.append((name,i,'medical deadline'))
            if boxes[i].first and t>boxes[i].first_deadline_s+1e-8: issues.append((name,i,'first-batch deadline'))
        recharge=end+charging_time_s(soc,resources.transport_batteries[mid][1])
        if not isclose(recharge,r['battery_recharged_s'],abs_tol=3e-6): issues.append((name,'recharge time mismatch'))
        by_craft[uid].append((start,end,name))
        by_battery[bid].append((start,recharge,name))
    if seen!=Counter({i:1 for i in boxes}): issues.append(('all','box coverage',[(i,seen[i]) for i in boxes if seen[i]!=1]))
    for uid,events in by_craft.items():
        for a,b in zip(sorted(events),sorted(events)[1:]):
            if b[0]<a[1]-1e-6: issues.append((uid,'craft overlap',a[2],b[2]))
    for bid,events in by_battery.items():
        for a,b in zip(sorted(events),sorted(events)[1:]):
            if b[0]<a[1]-1e-6: issues.append((bid,'battery/charge overlap',a[2],b[2]))
    if rows:
        actual={'sorties':len(rows),'energy_kwh':sum(r['energy_kwh'] for r in rows),
                'makespan_s':max(r['return_s'] for r in rows),
                'weighted_lateness_s':sum(boxes[i].priority*max(0,t-boxes[i].expected_s) for i,t in all_delivery.items() if boxes[i].kind!='医疗物资')}
        for key,value in actual.items():
            if not isclose(value,metrics[key],abs_tol=.01): issues.append(('all',key,'metric mismatch'))
    return issues


def main():
    data=json.loads(SOURCE.read_text(encoding='utf-8'))
    nodes,models,boxes=load_inputs(); resources=load_resources(); terrain=Terrain()
    checks={}
    for label in ('baseline','merged')+(('selected',) if 'selected' in data else ()):
        d=data[label]
        issues=inspect(d['missions'],d['metrics'],nodes,models,boxes,resources,terrain)
        print(label,'missions',len(d['missions']),'issues',len(issues))
        checks[label]={'issues':issues,'metrics':d['metrics']}
        for issue in issues[:30]: print(issue)
        if issues: raise SystemExit(1)
    # 有意破坏一份内存副本，证明检查器对关键时间错误有反应。
    altered=json.loads(json.dumps(data['merged']))
    altered['missions'][0]['delivery_s'][next(iter(altered['missions'][0]['delivery_s']))]+=500
    caught=inspect(altered['missions'],altered['metrics'],nodes,models,boxes,resources,terrain)
    if not any('delivery time mismatch' in str(x) for x in caught): raise AssertionError('未检出人工注入的交付时间错误')
    print('deliberate_delivery_corruption=DETECTED')
    report={'status':'passed','checks':checks,'injected_delivery_error_detected':True,
            'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
    SOURCE.with_name('q2_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__': main()
