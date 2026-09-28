# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""小幅地形/定位扰动的采样压力测试；不构成概率或连续鲁棒性保证。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from math import ceil,cos,pi
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources,make_leg
from diagnose_q3 import transport_phases
from radio import Position,gateway,link_budget

ROOT=Path(__file__).resolve().parent
SCENARIOS=(('nominal',0,0,0,0),('dem_plus_5m',0,0,0,5),
           ('alt_minus_5m',0,0,-5,0),('east_plus_5m',5,0,0,0),
           ('east_minus_5m',-5,0,0,0),('north_plus_5m',0,5,0,0),
           ('north_minus_5m',0,-5,0,0),('alt_minus_5m_dem_plus_5m',0,0,-5,5))


def adjusted(link,uplift,obstruction_loss):
    return link['margin_db']-(obstruction_loss if 0<=link['clearance_m']<uplift else 0)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--solution',type=Path,default=ROOT/'结果'/'q3_margin_candidate_30s.json')
    parser.add_argument('--step-s',type=float,default=5.0)
    args=parser.parse_args()
    if args.step_s<=0:raise ValueError('step-s 必须为正')
    q3=json.loads(args.solution.read_text(encoding='utf-8'))
    nodes,models,_=load_inputs();terrain=Terrain();radio=load_resources().radio
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    gate=gateway(nodes,radio)
    relays=q3['relay_sorties']
    hover={r['id']:Position(r['lon'],r['lat'],r['alt_m']) for r in relays}
    backhaul={r['id']:link_budget(hover[r['id']],gate,terrain,radio,
                                  '中继回传端','固定网关 G01','exact') for r in relays}
    result={}
    for name,east,north,down,uplift in SCENARIOS:
        count=below_one=outage=0;minimum=float('inf');examples=[];outage_by_mission=Counter()
        for mission in q3['transport_missions']:
            for phase in transport_phases(mission,nodes,models,legs):
                n=max(1,ceil((phase.t1-phase.t0)/args.step_s))
                for k in range(n+1):
                    t=phase.t0+(phase.t1-phase.t0)*k/n;p=phase.at(t)
                    latrad=p.lat*pi/180
                    q=Position(p.lon+east/(111320*cos(latrad)),p.lat+north/110540,p.alt_m+down)
                    direct=link_budget(q,gate,terrain,radio,'运输无人机','固定网关 G01','exact')
                    best=adjusted(direct,uplift,radio['传播参数::Lobs'])
                    if best<1:
                        for r in relays:
                            if r['ready_s']<=t<=r['service_end_s']:
                                access=link_budget(q,hover[r['id']],terrain,radio,
                                                   '运输无人机','中继接入端','exact')
                                margin=min(adjusted(access,uplift,radio['传播参数::Lobs']),
                                           adjusted(backhaul[r['id']],uplift,radio['传播参数::Lobs']))
                                best=max(best,margin)
                    count+=1;minimum=min(minimum,best)
                    below_one+=best<1;outage+=best<0
                    if best<0:outage_by_mission[mission['id']]+=1
                    if best<0 and len(examples)<5:examples.append((mission['id'],phase.kind,round(t,3),round(best,3)))
        result[name]={'samples':count,'min_best_margin_db':minimum,
                      'below_1db':below_one,'outages':outage,
                      'outages_by_mission':dict(outage_by_mission.most_common()),
                      'outage_examples':examples}
        print(name,result[name])
    output={'method':'每阶段最大固定时间步及逐格空间视线采样；统一 DEM 增高或运输机位置微扰，仅测试链路，不重算飞行避障/能耗',
            'step_s':args.step_s,'solution':args.solution.name,'scenarios':result}
    path=ROOT/'结果'/f'q3_perturb_{args.step_s:g}s_{args.solution.stem}.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
