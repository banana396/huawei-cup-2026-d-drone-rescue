# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""检验现有Q2首波调度能否由两处静止中继同时覆盖。"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources,make_leg
from diagnose_q3 import transport_phases
from radio import Position,direct,gateway,link_budget


ROOT=Path(__file__).resolve().parent


def candidates(nodes,terrain,radio):
    o=nodes['O01']; raw=[(z,n.lon,n.lat) for z,n in nodes.items()]
    raw += [(f'MID-{z}',(o.lon+n.lon)/2,(o.lat+n.lat)/2) for z,n in nodes.items() if z!='O01']
    result=[]
    for name,lon,lat in raw:
        ground=terrain.sample(lon,lat)
        for agl in (150,225,300):
            p=Position(lon,lat,ground+agl)
            b=link_budget(p,gateway(nodes,radio),terrain,radio,'中继回传端','固定网关 G01')
            if b['available']:result.append((f'{name}-{agl}',p))
    return result


def main():
    nodes,models,_=load_inputs();res=load_resources();terrain=Terrain();radio=res.radio
    rows=json.loads((ROOT/'结果'/'q2_results.json').read_text(encoding='utf-8'))['merged']['missions']
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    phases={r['id']:transport_phases(r,nodes,models,legs) for r in rows}
    cand=candidates(nodes,terrain,radio)
    for lon in [109.17+i*.006 for i in range(21)]:
        for lat in [23.005+j*.004 for j in range(20)]:
            try: ground=terrain.sample(lon,lat)
            except ValueError: continue
            p=Position(lon,lat,ground+300)
            if link_budget(p,gateway(nodes,radio),terrain,radio,'中继回传端','固定网关 G01')['available']:
                cand.append((f'GRID-{lon:.3f}-{lat:.3f}',p))
    for t in range(940,1141,20):
        blind=[]
        for mid,seq in phases.items():
            p=next((p for p in seq if p.t0<=t<=p.t1),None)
            if p:
                pos=p.at(t)
                if not direct(pos,nodes,terrain,radio)['available']:blind.append((mid,pos))
        masks=[]
        for name,hover in cand:
            mask=sum(1<<i for i,(_,pos) in enumerate(blind) if link_budget(pos,hover,terrain,radio,'运输无人机','中继接入端')['available'])
            masks.append((name,mask))
        full=(1<<len(blind))-1
        single=[name for name,m in masks if m==full]
        pairs=[(a,b) for i,(a,ma) in enumerate(masks) for b,mb in masks[i+1:] if ma|mb==full]
        best=max((int(m).bit_count() for _,m in masks),default=0)
        print(t,'blind',len(blind),'best_single',best,'single_solutions',single[:3],'pair_solutions',pairs[:3])


if __name__=='__main__':main()
