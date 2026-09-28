# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""在统一时间网格上诊断两架中继的空间覆盖需求。"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources,make_leg
from diagnose_q3 import transport_phases
from radio import Position,direct,gateway,link_budget


ROOT=Path(__file__).resolve().parent
CANDIDATE_IDS=['MID-S008-300','S010-225','MID-S003-225','S004-300',
               'S007-150','GRID-109.278-23.025-300']


def candidate_positions(nodes,terrain):
    o=nodes['O01']; found={}
    for name in CANDIDATE_IDS:
        stem,height=name.rsplit('-',1)
        if stem.startswith('MID-'):
            z=nodes[stem[4:]]; lon=(o.lon+z.lon)/2; lat=(o.lat+z.lat)/2
        elif stem.startswith('GRID-'):
            _,x,y=stem.split('-');lon=float(x);lat=float(y)
        else:
            z=nodes[stem]; lon=z.lon; lat=z.lat
        found[name]=Position(lon,lat,terrain.sample(lon,lat)+float(height))
    return found


def main():
    nodes,models,_=load_inputs(); resources=load_resources(); terrain=Terrain(); radio=resources.radio
    seed=len(sys.argv)>1 and sys.argv[1]=='seed'
    if seed:
        missions=json.loads((ROOT/'结果'/'q3_transport_seed.json').read_text(encoding='utf-8'))['missions']
    else:
        missions=json.loads((ROOT/'结果'/'q2_results.json').read_text(encoding='utf-8'))['merged']['missions']
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    phases={m['id']:transport_phases(m,nodes,models,legs) for m in missions}
    cands=candidate_positions(nodes,terrain)
    backhaul={name:link_budget(p,gateway(nodes,radio),terrain,radio,'中继回传端','固定网关 G01') for name,p in cands.items()}
    print('backhaul',{k:round(v['margin_db'],2) for k,v in backhaul.items()})
    times=list(range(0,int(max(m['return_s'] for m in missions))+21,20))
    rows=[]; uncovered=[]; need_two=0; blank=0
    for t in times:
        blind=[]
        for mid,seq in phases.items():
            p=next((p for p in seq if p.t0-1e-8<=t<=p.t1+1e-8),None)
            if p is None: continue
            pos=p.at(t)
            if direct(pos,nodes,terrain,radio)['available']: continue
            covered=[]
            for name,hover in cands.items():
                if not backhaul[name]['available']: continue
                link=link_budget(pos,hover,terrain,radio,'运输无人机','中继接入端')
                if link['available']: covered.append(name)
            blind.append({'mission':mid,'position':[pos.lon,pos.lat,pos.alt_m],'candidate_ids':covered})
        if not blind: blank+=1; continue
        names=list(cands)
        possible=[]
        for k in (1,2):
            for combo in itertools.combinations(names,k):
                if all(any(x in item['candidate_ids'] for x in combo) for item in blind): possible.append(combo)
            if possible: break
        if not possible: uncovered.append((t,[x['mission'] for x in blind]))
        elif len(possible[0])==2: need_two+=1
        rows.append({'t':t,'blind':blind,'cover_options':[list(x) for x in possible]})
    report={'step_s':20,'times_with_no_blind':blank,'times_with_blind':len(rows),
            'times_requiring_two':need_two,'times_uncovered_by_candidates':len(uncovered),
            'uncovered_examples':uncovered[:20],'rows':rows}
    path=ROOT/'结果'/('q3_seed_timeline_diagnostic.json' if seed else 'q3_timeline_diagnostic.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in report.items() if k!='rows'})


if __name__=='__main__': main()
