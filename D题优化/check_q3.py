# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""第三问独立核验：运输账、两架中继实体/能源、逐段时空通信。"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from math import ceil, isclose
from pathlib import Path

from check_q2 import inspect as inspect_transport
from d_common import G, Terrain, charging_time_s, horizontal_distance_m, load_inputs, load_resources, make_leg, Node
from diagnose_q3 import transport_phases
from radio import Position, direct, relay_path

ROOT=Path(__file__).resolve().parent


def inspect(data, step_s=5, step_pixels=.4):
    nodes,models,boxes=load_inputs();res=load_resources();terrain=Terrain()
    missions=data['transport_missions'];relays=data['relay_sorties'];issues=[]
    delivered={i:t for m in missions for i,t in m['delivery_s'].items()}
    metrics={'sorties':len(missions),'energy_kwh':sum(m['energy_kwh'] for m in missions),
             'makespan_s':max(m['return_s'] for m in missions),
             'weighted_lateness_s':sum(boxes[i].priority*max(0,t-boxes[i].expected_s)
                                       for i,t in delivered.items() if boxes[i].kind!='医疗物资')}
    issues.extend(inspect_transport(missions,metrics,nodes,models,boxes,res,terrain))
    by_craft=defaultdict(list);by_component=defaultdict(list)
    for r in relays:
        name=r['id'];p=Position(r['lon'],r['lat'],r['alt_m']);m=res.relay_models['R']
        if r['craft'] not in res.relay_craft:issues.append((name,'invalid relay craft'))
        if r['component'] not in {f'R-EC-{i:02d}' for i in range(1,7)}:issues.append((name,'invalid energy component'))
        agl=r['alt_m']-terrain.sample(p.lon,p.lat)
        if not (0<agl<=m.max_agl_m+1e-7):issues.append((name,'hover AGL'))
        d=horizontal_distance_m(nodes['O01'],Node('H',p.lon,p.lat,p.alt_m))
        cruise=terrain.line_max(nodes['O01'],Node('H',p.lon,p.lat,p.alt_m))+50
        cruise=max(cruise,p.alt_m)
        out=(cruise-nodes['O01'].ground_m)/m.climb_mps+d/m.cruise_mps+(cruise-p.alt_m)/m.descent_mps
        back=(cruise-p.alt_m)/m.climb_mps+d/m.cruise_mps+(cruise-nodes['O01'].ground_m)/m.descent_mps
        arrival=r['start_s']+m.prep_s+out
        ready=arrival+m.link_setup_s
        end=r['service_end_s'];return_s=end+back
        energy=(m.cruise_kw*(2*d/m.cruise_mps)/3600+
                m.takeoff_kg*G*((cruise-nodes['O01'].ground_m)+(cruise-p.alt_m))/(3_600_000*m.climb_eta)+
                m.hover_kw*(end-arrival)/3600+m.comm_kw*(end-ready)/3600)
        if r['start_s']<0 or not (r['start_s']<arrival<ready<=end<return_s):issues.append((name,'time order'))
        for key,calc in [('arrival_s',arrival),('ready_s',ready),('return_s',return_s),('energy_kwh',energy),
                         ('return_soc',1-energy/m.energy_kwh),
                         ('component_recharged_s',return_s+charging_time_s(1-energy/m.energy_kwh,res.relay_components['R'][1]))]:
            if not isclose(r[key],calc,abs_tol=5e-6):issues.append((name,key,'mismatch',r[key],calc))
        if energy>(1-m.reserve)*m.energy_kwh+1e-8:issues.append((name,'energy reserve'))
        by_craft[r['craft']].append((r['start_s'],return_s+m.turnaround_s,name))
        by_component[r['component']].append((r['start_s'],r['component_recharged_s'],name))
    for label,collection in [('relay craft',by_craft),('energy component',by_component)]:
        for id,events in collection.items():
            for a,b in zip(sorted(events),sorted(events)[1:]):
                if b[0]<a[1]-1e-6:issues.append((label,id,'overlap',a[2],b[2],a[1]-b[0]))
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    phases=[p for m in missions for p in transport_phases(m,nodes,models,legs)]
    samples=0;blind=0;relay_covered=0;min_margin=float('inf');uncovered=[]
    for phase in phases:
        n=max(1,ceil((phase.t1-phase.t0)/step_s))
        for k in range(n+1):
            t=phase.t0+(phase.t1-phase.t0)*k/n;pos=phase.at(t);samples+=1
            direct_link=direct(pos,nodes,terrain,res.radio,step_pixels)
            if direct_link['available']:
                min_margin=min(min_margin,direct_link['margin_db']);continue
            blind+=1;active=[r for r in relays if r['ready_s']-1e-8<=t<=r['service_end_s']+1e-8]
            working=[]
            for r in active:
                h=Position(r['lon'],r['lat'],r['alt_m'])
                path=relay_path(pos,h,nodes,terrain,res.radio,step_pixels)
                if path['available']:working.append((r['id'],path['margin_db']))
            if working:
                relay_covered+=1;min_margin=min(min_margin,max(m for _,m in working))
            else:
                if len(uncovered)<30:uncovered.append((phase.mission,phase.kind,round(t,3),len(active)))
    if uncovered:issues.append(('communication uncovered',uncovered))
    return issues,{'sample_interval_max_s':step_s,'los_step_max_pixels':step_pixels,'samples':samples,'direct_blind_samples':blind,
                   'relay_covered_samples':relay_covered,'min_available_margin_db':round(min_margin,4),
                   'transport_missions':len(missions),'relay_sorties':len(relays),
                   'makespan_s':max(max(m['return_s'] for m in missions),max(r['return_s'] for r in relays)),
                   'transport_energy_kwh':metrics['energy_kwh'],
                   'relay_energy_kwh':sum(r['energy_kwh'] for r in relays),
                   'weighted_lateness_s':metrics['weighted_lateness_s']}


def main():
    official=ROOT/'结果'/'q3_solution.json'
    p=Path(sys.argv[1]) if len(sys.argv)>1 else official
    data=json.loads(p.read_text(encoding='utf-8'))
    issues,metrics=inspect(data)
    print('Q3 check issues',len(issues));print(metrics)
    for issue in issues[:30]:print(issue)
    if issues:raise SystemExit(1)
    if p.resolve()==official.resolve():
        report={'status':'passed_sampled_verification','metrics':metrics,'issues':issues}
        (ROOT/'结果'/'q3_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        data['status']='passed_sampled_verification'
        p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
