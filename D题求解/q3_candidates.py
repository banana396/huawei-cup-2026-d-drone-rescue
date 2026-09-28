# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""中继悬停候选点粗筛；仅用于寻找可行方向。"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources
from radio import Position,gateway,link_budget


ROOT=Path(__file__).resolve().parent


def main():
    nodes,_,_=load_inputs(); terrain=Terrain(); radio=load_resources().radio
    diag=json.loads((ROOT/'结果'/'q3_direct_diagnostic.json').read_text(encoding='utf-8'))
    blind=[s for s in diag['samples'] if not s['direct']]
    by_mission=defaultdict(list)
    for s in blind: by_mission[s['mission']].append(s)
    coarse=[s for seq in by_mission.values() for s in seq[::5]]
    raw=[]
    for n in nodes.values(): raw.append((n.id,n.lon,n.lat))
    o=nodes['O01']
    for n in nodes.values():
        if n.id!='O01': raw.append((f'MID-{n.id}',(o.lon+n.lon)/2,(o.lat+n.lat)/2))
    candidates=[]
    for name,lon,lat in raw:
        ground=terrain.sample(lon,lat)
        for agl in (150,225,300):
            hover=Position(lon,lat,ground+agl)
            back=link_budget(hover,gateway(nodes,radio),terrain,radio,'中继回传端','固定网关 G01')
            if not back['available']: continue
            covered=[]
            for i,s in enumerate(coarse):
                p=Position(s['lon'],s['lat'],s['alt_m'])
                access=link_budget(p,hover,terrain,radio,'运输无人机','中继接入端')
                if access['available']: covered.append(i)
            candidates.append({'id':f'{name}-{agl}','lon':lon,'lat':lat,'alt_m':hover.alt_m,
                               'ground_m':ground,'backhaul_margin_db':back['margin_db'],
                               'covered':covered})
    remaining=set(range(len(coarse))); selected=[]
    while remaining:
        choice=max(candidates,key=lambda c:len(set(c['covered'])&remaining))
        gain=len(set(choice['covered'])&remaining)
        if gain==0: break
        selected.append((choice['id'],gain))
        remaining-=set(choice['covered'])
    result={'blind_samples':len(blind),'coarse_samples':len(coarse),'candidate_count':len(candidates),
            'greedy_selected':selected,'uncovered_coarse':len(remaining),
            'top_candidates':sorted([{'id':c['id'],'lon':c['lon'],'lat':c['lat'],'alt_m':c['alt_m'],
                                      'ground_m':c['ground_m'],'coarse_coverage':len(c['covered'])} for c in candidates],
                                     key=lambda c:-c['coarse_coverage'])[:20]}
    path=ROOT/'结果'/'q3_candidate_diagnostic.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(result)


if __name__=='__main__': main()
