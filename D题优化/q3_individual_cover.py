# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""查找每个运输架次的单点中继覆盖候选。"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources
from q3_bottleneck import candidates
from radio import Position,link_budget
from relay_flight import relay_route


ROOT=Path(__file__).resolve().parent


def main():
    nodes,_,_=load_inputs();terrain=Terrain();res=load_resources();radio=res.radio
    diag=json.loads((ROOT/'结果'/'q3_seed_direct_diagnostic.json').read_text(encoding='utf-8'))
    blind=defaultdict(list)
    for s in diag['samples']:
        if not s['direct']: blind[s['mission']].append(Position(s['lon'],s['lat'],s['alt_m']))
    cand=candidates(nodes,terrain,radio)
    out={}
    for mid,positions in sorted(blind.items()):
        masks=[]; viable=[]
        for name,p in cand:
            mask=0
            for i,x in enumerate(positions):
                if link_budget(x,p,terrain,radio,'运输无人机','中继接入端')['available']:mask|=1<<i
            masks.append((name,mask))
            if mask==(1<<len(positions))-1:
                flight=relay_route(p,nodes,terrain,res.relay_models['R'])
                viable.append((flight['flight_energy_kwh'],name))
        pairs=[];full=(1<<len(positions))-1
        if not viable:
            for i,(a,ma) in enumerate(masks):
                for b,mb in masks[i+1:]:
                    if ma|mb==full:pairs.append((a,b))
        out[mid]={'single':sorted(viable)[:5],'pairs':pairs[:20]}
        print(mid,'blind_samples',len(positions),'single_relay_candidates',len(viable),
              'best',sorted(viable)[:3],'pair_options',pairs[:3])
    (ROOT/'结果'/'q3_individual_cover.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
