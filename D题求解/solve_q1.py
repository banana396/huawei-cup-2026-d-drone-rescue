# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""第一问单点组批求解。AI 辅助代码，正式参赛提交前请按附件4补全披露信息。"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from d_common import Terrain, load_inputs, make_leg, max_safe_payload, roundtrip


OUT = Path(__file__).resolve().parent / "结果"
RESERVES = [0.10, 0.15, 0.20, 0.25, 0.30]


def solve_zone(zone, zone_boxes, models, out, back, reserve, objective="sorties_first"):
    n=len(zone_boxes)
    full=(1<<n)-1
    weights=[b.kg for b in zone_boxes]
    volumes=[b.m3 for b in zone_boxes]
    w=[0.0]*(full+1); v=[0.0]*(full+1); count=[0]*(full+1)
    for mask in range(1,full+1):
        bit=mask&-mask; i=bit.bit_length()-1; rest=mask^bit
        w[mask]=w[rest]+weights[i]
        v[mask]=v[rest]+volumes[i]
        count[mask]=count[rest]+1
    candidates=[[] for _ in range(n)]
    for mask in range(1,full+1):
        for m in models.values():
            if w[mask]>m.max_kg+1e-9 or v[mask]>m.max_m3+1e-9: continue
            energy,time,soc=roundtrip(m,out,back,w[mask],count[mask])
            if soc+1e-9<reserve: continue
            lowest=(mask&-mask).bit_length()-1
            candidates[lowest].append((mask,m.id,energy,time,soc))

    @lru_cache(None)
    def dp(covered):
        if covered==full: return (0,0.0,0.0,())
        missing=full^covered
        lowest=(missing&-missing).bit_length()-1
        best=None
        for mask,model,energy,time,soc in candidates[lowest]:
            if mask&covered: continue
            tail=dp(covered|mask)
            if tail is None: continue
            value=(1+tail[0],energy+tail[1],time+tail[2],((mask,model,energy,time,soc),)+tail[3])
            key=lambda v: v[:3] if objective=="sorties_first" else (v[1],v[0],v[2])
            if best is None or key(value)<key(best): best=value
        return best

    best=dp(0)
    if best is None: return None
    trips=[]
    for mask,mid,energy,time,soc in best[3]:
        trips.append({"zone":zone,"model":mid,"boxes":[zone_boxes[i].id for i in range(n) if mask>>i&1],
                      "kg":round(w[mask],6),"m3":round(v[mask],6),
                      "energy_kwh":round(energy,9),"operation_s":round(time,6),"return_soc":round(soc,9)})
    return trips


def main():
    nodes,models,boxes=load_inputs()
    terrain=Terrain()
    groups=defaultdict(list)
    for box in boxes.values(): groups[box.zone].append(box)
    legs={z:(make_leg(terrain,nodes['O01'],nodes[z]),make_leg(terrain,nodes[z],nodes['O01'])) for z in sorted(groups)}
    result={"assumptions":{
        "horizontal_energy":"Eusable * horizontal_distance / equivalent_range(current_payload)",
        "climb_energy":"(empty_mass_including_battery + current_payload) * 9.80665 * climb_m / (3600000 * climb_efficiency)",
        "status":"这两个分项公式是参赛队待核验的建模假设，不是题面明示公式。",
        "distance":"按两端平均纬度的局部WGS84椭球尺度计算，与经纬度直线穿格对应；节点作业海拔取节点表。",
        "objective":"主方案按架次数、总能耗、累计作业时间依次最小化；20%余量另给能耗优先对照。本第一问不计实体机和电池周转。"},
        "baseline_reserve":0.20,"zones":{},"sensitivity":{}}
    for reserve in RESERVES:
        scenario={"reserve":reserve,"safe_payload_kg":{},"trips":[],"infeasible_zones":[]}
        for z in sorted(groups):
            out,back=legs[z]
            scenario['safe_payload_kg'][z]={m.id:None if (x:=max_safe_payload(m,out,back,reserve)) is None else round(x,6) for m in models.values()}
            trips=solve_zone(z,groups[z],models,out,back,reserve)
            if trips is None: scenario['infeasible_zones'].append(z)
            else: scenario['trips'].extend(trips)
        for i,t in enumerate(scenario['trips'],1): t['id']=f'Q1-R{round(reserve*100):02d}-{i:03d}'
        scenario['metrics']={"sorties":len(scenario['trips']),
                             "energy_kwh":round(sum(t['energy_kwh'] for t in scenario['trips']),6),
                             "operation_s":round(sum(t['operation_s'] for t in scenario['trips']),3),
                             "model_sorties":dict(Counter(t['model'] for t in scenario['trips']))}
        result['sensitivity'][str(round(reserve*100))]=scenario
    result['zones']={z:{"box_count":len(groups[z]),"leg_distance_m":round(legs[z][0].distance_m,3),
                        "cruise_alt_m":round(legs[z][0].cruise_alt_m,3),
                        "out_climb_m":round(legs[z][0].climb_m,3),
                        "back_climb_m":round(legs[z][1].climb_m,3)} for z in sorted(groups)}
    alternative=[]
    for z in sorted(groups):
        out,back=legs[z]
        trips=solve_zone(z,groups[z],models,out,back,.20,"energy_first")
        if trips is None: raise RuntimeError(f'20%能耗优先方案不可行: {z}')
        alternative.extend(trips)
    for i,t in enumerate(alternative,1): t['id']=f'Q1-E20-{i:03d}'
    result['alternative_20_energy_first']={
        "trips":alternative,
        "metrics":{"sorties":len(alternative),
                   "energy_kwh":round(sum(t['energy_kwh'] for t in alternative),6),
                   "operation_s":round(sum(t['operation_s'] for t in alternative),3),
                   "model_sorties":dict(Counter(t['model'] for t in alternative))}}
    OUT.mkdir(exist_ok=True)
    path=OUT/'q1_results_v2.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(path)
    for k,s in result['sensitivity'].items(): print(k+'%:',s['metrics'],'infeasible',s['infeasible_zones'])
    print('20% energy-first:',result['alternative_20_energy_first']['metrics'])


if __name__=='__main__': main()
