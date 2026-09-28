# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""筛选 Q3-024 单点中继站位的空间链路最低裕量，不代替资源排程验证。"""
from __future__ import annotations

import json
from math import ceil
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources,make_leg
from diagnose_q3 import transport_phases
from q3_bottleneck import candidates
from radio import direct,gateway,link_budget
from relay_flight import relay_route

ROOT=Path(__file__).resolve().parent


def main():
    q3=json.loads((ROOT/'结果'/'q3_margin_candidate_30s.json').read_text(encoding='utf-8'))
    mission=next(m for m in q3['transport_missions'] if m['id']=='Q3-024')
    nodes,models,_=load_inputs();terrain=Terrain();res=load_resources();radio=res.radio
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    samples=[]
    for phase in transport_phases(mission,nodes,models,legs):
        n=max(1,ceil((phase.t1-phase.t0)/5))
        for k in range(n+1):
            t=phase.t0+(phase.t1-phase.t0)*k/n;p=phase.at(t)
            d=direct(p,nodes,terrain,radio,'exact')['margin_db']
            if d<3:samples.append((p,d))
    ranked=[]
    for name,hover in candidates(nodes,terrain,radio):
        backhaul=link_budget(hover,gateway(nodes,radio),terrain,radio,'中继回传端','固定网关 G01','exact')['margin_db']
        worst=float('inf')
        for p,d in samples:
            access=link_budget(p,hover,terrain,radio,'运输无人机','中继接入端','exact')['margin_db']
            worst=min(worst,max(d,min(access,backhaul)))
            if worst<1:break
        if worst>=1:
            route=relay_route(hover,nodes,terrain,res.relay_models['R'])
            ranked.append((round(worst,3),round(route['flight_energy_kwh'],3),name))
    ranked.sort(reverse=True)
    print('samples',len(samples),'sites_with_at_least_1db_at_all_samples',len(ranked))
    for item in ranked[:30]:print(item)


if __name__=='__main__':main()
