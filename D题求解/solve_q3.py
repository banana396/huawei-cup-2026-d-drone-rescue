# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""构造第三问运输-中继联合可行解；所有时间单位秒，能量单位kWh。"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from d_common import Terrain, charging_time_s, load_inputs, load_resources
from q3_timeline import candidate_positions
from q3_individual_cover import candidates
from radio import Position
from relay_flight import relay_route

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '结果'
HARD_SITES = {0: ('S007-150', 'GRID-109.278-23.025-300'),
              1: ('S007-150', 'S004-300'),
              2: ('S007-150', 'MID-S008-300')}
SOFT_PAIRS = {'Q3-016': ('S004-300', 'S007-150'),
              'Q3-019': ('S001-150', 'S010-300')}


def main():
    official_run=len(sys.argv)==1
    mode=sys.argv[1] if len(sys.argv)>1 else 'due'
    if mode not in ('ratio','weight','due','duration','relay_first'):
        raise ValueError(f'未知软任务排序模式: {mode}')
    guard_s=float(sys.argv[2]) if len(sys.argv)>2 else (30.0 if official_run else 0.0)
    if guard_s<0:raise ValueError('额外中继时间护栏必须非负')
    nodes, models, boxes = load_inputs()
    terrain = Terrain(); resources = load_resources(); relay = resources.relay_models['R']
    missions = json.loads((OUT/'q3_transport_seed.json').read_text(encoding='utf-8'))['missions']
    diagnostic = json.loads((OUT/'q3_seed_direct_diagnostic.json').read_text(encoding='utf-8'))
    individual = json.loads((OUT/'q3_individual_cover.json').read_text(encoding='utf-8'))
    sites = dict(candidates(nodes, terrain, resources.radio))
    sites.update(candidate_positions(nodes, terrain))
    blind = defaultdict(list)
    for s in diagnostic['samples']:
        if not s['direct']: blind[s['mission']].append(s['t'])
    if guard_s:
        for index,m in enumerate(missions[:15]):
            wave=0 if index<8 else 1 if index<12 else 2
            delta=2*guard_s*wave
            if not delta:continue
            m['start_s']=round(m['start_s']+delta,6)
            m['return_s']=round(m['return_s']+delta,6)
            m['delivery_s']={k:round(v+delta,6) for k,v in m['delivery_s'].items()}
            m['battery_recharged_s']=round(m['battery_recharged_s']+delta,6)
            blind[m['id']]=[t+delta for t in blind[m['id']]]
    craft_avail = {id: 0.0 for id in resources.relay_craft}
    component_avail = {f'R-EC-{i:02d}': 0.0 for i in range(1,7)}
    sorties = []

    def launch(craft_id, name, desired_start, service_end):
        p = sites[name]; route = relay_route(p,nodes,terrain,relay)
        comp = min(component_avail,key=lambda k: max(component_avail[k], desired_start))
        start = max(desired_start, craft_avail[craft_id], component_avail[comp])
        arrival = start + relay.prep_s + route['out_s']
        ready = arrival + relay.link_setup_s
        end = max(service_end,ready)
        return_s = end + route['back_s']
        energy = route['flight_energy_kwh'] + relay.hover_kw*(end-arrival)/3600 + relay.comm_kw*(end-ready)/3600
        if energy > (1-relay.reserve)*relay.energy_kwh+1e-8:
            raise RuntimeError(f'中继能量超限: {craft_id} {name}: {energy:.5f}')
        component_avail[comp] = return_s + charging_time_s(1-energy/relay.energy_kwh,
                                                             resources.relay_components['R'][1])
        craft_avail[craft_id] = return_s + relay.turnaround_s
        r={'id':f'R-{len(sorties)+1:03d}','craft':craft_id,'component':comp,'site':name,
           'lon':p.lon,'lat':p.lat,'alt_m':p.alt_m,'agl_m':p.alt_m-terrain.sample(p.lon,p.lat),
           'start_s':round(start,6),'arrival_s':round(arrival,6),'ready_s':round(ready,6),
           'service_end_s':round(end,6),'return_s':round(return_s,6),
           'component_recharged_s':round(component_avail[comp],6),
           'energy_kwh':round(energy,9),'return_soc':round(1-energy/relay.energy_kwh,9),
           'route':route}
        sorties.append(r)
        return r

    # 第一架中继持续覆盖三波硬时限任务；第二架在窗口间返回、换能、转场。
    hard = missions[:15]
    waves=[hard[:8],hard[8:12],hard[12:15]]
    wave_end = [max((max(blind[m['id']]) for m in wave if blind[m['id']]),default=0)+pad+guard_s
                for wave,pad in zip(waves,(10,12,20))]
    r1=launch('R01','S007-150',0,wave_end[-1])
    r2a=launch('R02',HARD_SITES[0][1],0,wave_end[0])
    r2b=launch('R02',HARD_SITES[1][1],craft_avail['R02'],wave_end[1])
    r2c=launch('R02',HARD_SITES[2][1],craft_avail['R02'],wave_end[2])
    for i,(wave,second) in enumerate(zip(waves,[r2a,r2b,r2c])):
        first_blind=min((min(blind[m['id']]) for m in wave if blind[m['id']]),default=float('inf'))
        print('wave',i+1,'first_blind',first_blind,'ready',r1['ready_s'],second['ready_s'])
        if max(r1['ready_s'],second['ready_s'])>first_blind+1e-6:
            raise RuntimeError(f'硬时限第{i+1}波中继就位晚于首个盲点')

    # 后续任务允许在不同运输实体与不同中继上并行；默认按最早期望交付时间排序。
    # 另保留几种启发式排序，用于同口径候选比较。
    transport_craft_end = defaultdict(float)
    transport_battery_ready = defaultdict(float)
    for m in hard:
        transport_craft_end[m['craft']] = max(transport_craft_end[m['craft']],m['return_s'])
        transport_battery_ready[m['battery']] = max(transport_battery_ready[m['battery']],m['battery_recharged_s'])
    mission_relays={}
    def order_key(m):
        ids=[i for stop in m['stops'] for i in stop['boxes']]
        weight=sum(boxes[i].priority for i in ids)
        duration=m['return_s']-m['start_s']
        if mode=='weight':return (-weight,duration,m['id'])
        if mode=='due':return (min(boxes[i].expected_s for i in ids),-weight,m['id'])
        if mode=='duration':return (duration,-weight,m['id'])
        if mode=='relay_first':return (not bool(blind[m['id']]),duration/max(weight,1),m['id'])
        return (bool(blind[m['id']]),duration/max(weight,1),m['id'])
    for m in sorted(missions[15:],key=order_key):
        mission_id=m['id']; old_start=m['start_s']
        start=max(6000.0,transport_craft_end[m['craft']],transport_battery_ready[m['battery']])
        options=individual.get(mission_id)
        if options:
            names=SOFT_PAIRS.get(mission_id)
            if names is None:
                if not options['single']: raise RuntimeError(f'{mission_id}缺少单点中继方案')
                names=('MID-S003-225',) if guard_s and mission_id=='Q3-024' else (options['single'][0][1],)
            rel_first=min(blind[mission_id])-old_start
            rel_last=max(blind[mission_id])-old_start
            assignments=[]
            for name in names:
                # 为首次盲点预留30秒及可选额外护栏；两架中继任务不能并发超出资源数。
                p=sites[name]; route=relay_route(p,nodes,terrain,relay)
                lead=relay.prep_s+route['out_s']+relay.link_setup_s
                c=min(craft_avail,key=lambda x:max(craft_avail[x],start+rel_first-lead-30-guard_s))
                desired=max(craft_avail[c],start+rel_first-lead-30-guard_s)
                # 先估算就位时间，再据此修正运输起飞时间。
                component=min(component_avail,key=lambda x:max(component_avail[x],desired))
                earliest=max(desired,component_avail[component])+lead
                start=max(start,earliest-rel_first+30+guard_s)
                assignments.append((c,name))
                # 暂占机位，确保双中继任务取不同实体。
                craft_avail[c]=float('inf')
            for c,_ in assignments:craft_avail[c]=next((r['return_s']+relay.turnaround_s for r in reversed(sorties) if r['craft']==c),0.0)
            chosen=[]
            for c,name in assignments:
                p=sites[name]; route=relay_route(p,nodes,terrain,relay)
                lead=relay.prep_s+route['out_s']+relay.link_setup_s
                desired=max(craft_avail[c],start+rel_first-lead-30-guard_s)
                rr=launch(c,name,desired,start+rel_last+20+guard_s)
                if rr['ready_s']>start+rel_first+1e-6:
                    raise RuntimeError(f'{mission_id}中继就位延迟')
                chosen.append(rr['id'])
            mission_relays[mission_id]=chosen
        delta=start-old_start
        m['start_s']=round(start,6)
        m['return_s']=round(m['return_s']+delta,6)
        m['delivery_s']={k:round(v+delta,6) for k,v in m['delivery_s'].items()}
        m['battery_recharged_s']=round(m['battery_recharged_s']+delta,6)
        transport_craft_end[m['craft']]=m['return_s']
        transport_battery_ready[m['battery']]=m['battery_recharged_s']

    result={'status':'candidate_pending_independent_verification',
            'assumptions':['水平续航折算电耗+爬升势能/效率','通信在爬升、巡航、下降和交接全过程连续检查；数值检查采用有限步长',
                           '中继回程后300秒周转；能源组件依题设分段充电；中继悬停持续供电'],
            'transport_missions':missions,'relay_sorties':sorties,'mission_relays':mission_relays,
            'hard_wave_sites':HARD_SITES}
    path=OUT/('q3_solution.json' if official_run else
              f'q3_margin_candidate_{guard_s:g}s.json' if guard_s else
              f'q3_candidate_{mode}.json')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(path,'transport',len(missions),'relay sorties',len(sorties),
          'makespan',max(max(m['return_s'] for m in missions),max(r['return_s'] for r in sorties)),
          'transport energy',sum(m['energy_kwh'] for m in missions),
          'relay energy',sum(r['energy_kwh'] for r in sorties))
    print('hard relay readiness',[(r['site'],r['ready_s'],r['service_end_s']) for r in sorties[:4]])


if __name__=='__main__':main()
