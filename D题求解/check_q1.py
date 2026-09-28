# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""第一问结果独立复核：不信任输出中的质量、体积、能耗及SOC字段。"""
from __future__ import annotations

import json
import hashlib
from collections import Counter, defaultdict
from math import isclose
from pathlib import Path

import openpyxl

from d_common import G, Terrain, load_inputs, make_leg


HERE=Path(__file__).resolve().parent


def check():
    nodes,models,boxes=load_inputs()
    data=json.loads((HERE/'结果'/'q1_results_v2.json').read_text(encoding='utf-8'))
    dem=Terrain()
    legs={z:(make_leg(dem,nodes['O01'],nodes[z]),make_leg(dem,nodes[z],nodes['O01'])) for z in nodes if z!='O01'}
    errors=[]
    by_kind=defaultdict(list)
    for box in boxes.values(): by_kind[(box.zone,box.kind)].append(box)
    summary=HERE.parent/'2026年中国研究生数学建模竞赛赛题'/'D题'/'数据'/'无人机应急物资运输基础数据'/'物资需求与配送时限.xlsx'
    rows=openpyxl.load_workbook(summary,read_only=True,data_only=True).worksheets[0].values
    next(rows)
    for r in rows:
        if not r[0]: continue
        group=by_kind.get((r[0],r[1]),[])
        if len(group)!=r[2] or sum(b.first for b in group)!=r[3]:
            errors.append(('input',r[0],r[1],'summary count mismatch'))
        if any(abs(b.kg-r[4])>1e-9 or abs(b.m3-r[5])>1e-9 for b in group):
            errors.append(('input',r[0],r[1],'box mass/volume mismatch'))
    scenarios=list(data['sensitivity'].items())+[("20-energy-first",data['alternative_20_energy_first'])]
    for level,scenario in scenarios:
        reserve=.20 if level=="20-energy-first" else float(level)/100
        for zone,payloads in scenario.get('safe_payload_kg',{}).items():
            out,back=legs[zone]
            for mid,q in payloads.items():
                if q is None: continue
                m=models[mid]
                def payload_energy(x):
                    rg=m.range_empty_m-(m.range_empty_m-m.range_full_m)*(x/m.max_kg)**1.5
                    return (m.energy_kwh*out.distance_m/rg+(m.empty_kg+x)*G*out.climb_m/(3_600_000*m.climb_eta)
                            +m.energy_kwh*back.distance_m/m.range_empty_m+m.empty_kg*G*back.climb_m/(3_600_000*m.climb_eta))
                if q>m.max_kg+1e-6 or payload_energy(q)>(1-reserve)*m.energy_kwh+1e-6:
                    errors.append((level,zone,mid,'reported safe payload infeasible'))
                if q<m.max_kg-1e-4 and payload_energy(min(m.max_kg,q+0.001))<(1-reserve)*m.energy_kwh-1e-6:
                    errors.append((level,zone,mid,'reported safe payload not maximal'))
        seen=Counter()
        for trip in scenario['trips']:
            z=trip['zone']; mid=trip['model']
            if z not in legs or mid not in models: errors.append((level,trip['id'],'invalid ID')); continue
            m=models[mid]
            ids=trip['boxes']
            if not ids: errors.append((level,trip['id'],'empty trip')); continue
            if len(ids)!=len(set(ids)): errors.append((level,trip['id'],'duplicate in trip'))
            if any(i not in boxes for i in ids): errors.append((level,trip['id'],'unknown box')); continue
            for i in ids:
                seen[i]+=1
                if boxes[i].zone!=z: errors.append((level,trip['id'],'cross-zone'))
            kg=sum(boxes[i].kg for i in ids)
            m3=sum(boxes[i].m3 for i in ids)
            if kg>m.max_kg+1e-9 or m3>m.max_m3+1e-9: errors.append((level,trip['id'],'over capacity'))
            out,back=legs[z]
            def energy(leg,q):
                effective_range=m.range_empty_m-(m.range_empty_m-m.range_full_m)*(q/m.max_kg)**1.5
                return m.energy_kwh*leg.distance_m/effective_range+(m.empty_kg+q)*G*leg.climb_m/(3_600_000*m.climb_eta)
            e=energy(out,kg)+energy(back,0)
            soc=1-e/m.energy_kwh
            duration=(m.prep_s+len(ids)*m.load_box_s+m.handoff_base_s+len(ids)*m.handoff_box_s+
                      sum(x.climb_m/m.climb_mps+x.distance_m/m.cruise_mps+x.descent_m/m.descent_mps for x in (out,back)))
            for field,actual in [('kg',kg),('m3',m3),('energy_kwh',e),('return_soc',soc),('operation_s',duration)]:
                if not isclose(trip[field],actual,rel_tol=0,abs_tol=2e-6): errors.append((level,trip['id'],field+' mismatch'))
            if soc<reserve-1e-9: errors.append((level,trip['id'],'below reserve'))
        if scenario.get('infeasible_zones'):
            errors.append((level,'scenario','infeasible zones: '+str(scenario['infeasible_zones'])))
        if seen!=Counter({i:1 for i in boxes}):
            errors.append((level,'scenario','box coverage missing/duplicate: '+str([i for i in boxes if seen[i]!=1])))
    print('levels',list(data['sensitivity']),'boxes',len(boxes),'errors',len(errors))
    for e in errors[:40]: print(e)
    report={'status':'passed' if not errors else 'failed','issues':errors,
            'reserve_levels':list(data['sensitivity']),'boxes_per_scenario':len(boxes),
            'scenario_count':len(scenarios),
            'source_sha256':hashlib.sha256((HERE/'结果'/'q1_results_v2.json').read_bytes()).hexdigest()}
    (HERE/'结果'/'q1_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if errors: raise SystemExit(1)


if __name__=='__main__': check()
