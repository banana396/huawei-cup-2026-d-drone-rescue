# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""检查当前连续区间证书的临界时刻及已在位中继备选链路。"""
from __future__ import annotations

import json
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources,make_leg
from diagnose_q3 import transport_phases
from radio import Position,direct,relay_path

ROOT=Path(__file__).resolve().parent


def main():
    solution=json.loads((ROOT/'结果'/'q3_solution.json').read_text(encoding='utf-8'))
    certificate=json.loads((ROOT/'结果'/'q3_interval_certificate.json').read_text(encoding='utf-8'))
    item=certificate['limiting_interval'];time=(item['start_s']+item['end_s'])/2
    nodes,models,_=load_inputs();terrain=Terrain();radio=load_resources().radio
    mission=next(m for m in solution['transport_missions'] if m['id']==item['mission'])
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    phase=next(p for p in transport_phases(mission,nodes,models,legs) if p.t0<=time<=p.t1)
    pos=phase.at(time)
    choices={'direct':direct(pos,nodes,terrain,radio,'exact')['margin_db']}
    for relay in solution['relay_sorties']:
        if relay['ready_s']<=time<=relay['service_end_s']:
            hover=Position(relay['lon'],relay['lat'],relay['alt_m'])
            choices[relay['id']]=relay_path(pos,hover,nodes,terrain,radio,'exact')['margin_db']
    print({'mission':item['mission'],'time_s':time,'phase':phase.kind,
           'certified_interval_margin_db':item['margin_db'],'point_margins_db':choices})


if __name__=='__main__':main()
