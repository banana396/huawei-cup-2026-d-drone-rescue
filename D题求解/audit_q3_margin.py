# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""对 Q3 做安全裕量采样筛查；直连不足门槛时计入已在位中继备份。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from math import ceil
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources,make_leg
from diagnose_q3 import transport_phases
from radio import Position,direct,relay_path

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--step-s',type=float,default=5.0)
    parser.add_argument('--solution',type=Path,default=ROOT/'结果'/'q3_solution.json')
    args=parser.parse_args()
    if args.step_s<=0:raise ValueError('step-s 必须为正')
    q3=json.loads(args.solution.read_text(encoding='utf-8'))
    nodes,models,_=load_inputs();terrain=Terrain();radio=load_resources().radio
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    relays=q3['relay_sorties']
    hover={r['id']:Position(r['lon'],r['lat'],r['alt_m']) for r in relays}
    counts=Counter();worst=[];below_one_by_mission=Counter();below_one_windows={};min_best=float('inf');minimum_case=None
    for mission in q3['transport_missions']:
        for phase in transport_phases(mission,nodes,models,legs):
            n=max(1,ceil((phase.t1-phase.t0)/args.step_s))
            for k in range(n+1):
                t=phase.t0+(phase.t1-phase.t0)*k/n
                p=phase.at(t)
                d=direct(p,nodes,terrain,radio,'exact')['margin_db']
                best=d;path='direct'
                if d<3:
                    for r in relays:
                        if r['ready_s']<=t<=r['service_end_s']:
                            margin=relay_path(p,hover[r['id']],nodes,terrain,radio,'exact')['margin_db']
                            if margin>best:best=margin;path=r['id']
                counts['samples']+=1
                for threshold in (0,1,3):
                    if best<threshold:counts[f'below_{threshold}db']+=1
                    if d<threshold:counts[f'direct_below_{threshold}db']+=1
                if best<1:
                    below_one_by_mission[mission['id']]+=1
                    window=below_one_windows.setdefault(mission['id'],{'first_s':t,'last_s':t,'min_margin_db':best})
                    window['last_s']=t
                    window['min_margin_db']=min(window['min_margin_db'],best)
                    if path=='direct':counts['below_1db_without_effective_relay']+=1
                if best<min_best:
                    min_best=best
                    minimum_case={'mission':mission['id'],'phase':phase.kind,'time_s':round(t,6),
                                  'direct_margin_db':round(d,6),'best_path':path,
                                  'best_margin_db':round(best,6)}
                if best<3 and len(worst)<50:
                    worst.append({'mission':mission['id'],'phase':phase.kind,
                                  'time_s':round(t,6),'direct_margin_db':round(d,6),
                                  'best_path':path,'best_margin_db':round(best,6)})
    min_mission=next(m for m in q3['transport_missions'] if m['id']==minimum_case['mission'])
    min_phase=next(p for p in transport_phases(min_mission,nodes,models,legs)
                   if p.t0<=minimum_case['time_s']<=p.t1)
    min_pos=min_phase.at(minimum_case['time_s'])
    alternative_relays=[{'id':r['id'],'site':r['site'],
                         'active':r['ready_s']<=minimum_case['time_s']<=r['service_end_s'],
                         'margin_db':relay_path(min_pos,hover[r['id']],nodes,terrain,radio,'exact')['margin_db']}
                        for r in relays]
    alternative_relays.sort(key=lambda x:x['margin_db'],reverse=True)
    out={'method':'每阶段按固定最大时间步采样，空间视线逐格；非连续证明',
         'step_s':args.step_s,'counts':counts,'min_best_margin_db':min_best,
         'minimum_case':minimum_case,'below_1db_by_mission':below_one_by_mission,
         'below_1db_windows':below_one_windows,
         'minimum_case_relay_options':alternative_relays,
         'first_low_margin_examples':worst}
    label='' if args.solution.stem=='q3_solution' else f'_{args.solution.stem}'
    p=ROOT/'结果'/f'q3_margin_audit_{args.step_s:g}s{label}.json'
    p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(p,dict(counts),'min_best_margin_db',min_best,'minimum_case',minimum_case)
    print('below_1db_by_mission',dict(below_one_by_mission))
    print('below_1db_windows',below_one_windows)
    print('minimum_case_relay_options',alternative_relays[:6])
    for item in worst[:10]:print(item)


if __name__=='__main__':main()
