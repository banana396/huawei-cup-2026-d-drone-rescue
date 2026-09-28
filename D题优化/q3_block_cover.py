# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""查找各时间块由两处固定悬停点覆盖的候选对。"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources
from q3_bottleneck import candidates
from radio import Position,link_budget


ROOT=Path(__file__).resolve().parent
BLOCKS=[(700,1480),(3000,3900),(5680,6160),(9740,11340),(12000,13780),(14620,15240),(15780,16320)]


def main():
    nodes,_,_=load_inputs();terrain=Terrain();radio=load_resources().radio
    diag=json.loads((ROOT/'结果'/'q3_seed_timeline_diagnostic.json').read_text(encoding='utf-8'))
    cand=candidates(nodes,terrain,radio)
    # 在节点/中点外补充粗规则网格；先只用最大离地高度作试探。
    for lon in [109.17+i*.006 for i in range(21)]:
        for lat in [23.005+j*.004 for j in range(20)]:
            try: ground=terrain.sample(lon,lat)
            except ValueError: continue
            p=Position(lon,lat,ground+300)
            from radio import gateway
            if link_budget(p,gateway(nodes,radio),terrain,radio,'中继回传端','固定网关 G01')['available']:
                cand.append((f'GRID-{lon:.3f}-{lat:.3f}-300',p))
    for start,end in BLOCKS:
        demands=[]
        for r in diag['rows']:
            if start<=r['t']<=end and (r['t']-start)%40==0:
                demands.extend((r['t'],x['mission'],Position(*x['position'])) for x in r['blind'])
        full=(1<<len(demands))-1
        masks=[]
        for name,p in cand:
            mask=0
            for i,(_,_,pos) in enumerate(demands):
                if link_budget(pos,p,terrain,radio,'运输无人机','中继接入端')['available']: mask|=1<<i
            masks.append((name,mask))
        complete=[]; best=(0,None)
        for i,(a,ma) in enumerate(masks):
            for b,mb in masks[i+1:]:
                covered=(ma|mb).bit_count()
                if covered>best[0]:best=(covered,(a,b))
                if ma|mb==full and len(complete)<10:complete.append((a,b))
        print((start,end),'demands',len(demands),'candidates',len(cand),'complete_pairs',complete[:4],
              'best_covered',best[0], 'best_pair',best[1])


if __name__=='__main__':main()
