# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""第二问方案的第三问直连盲区诊断；采样结果不能单独证明连续通信。"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from d_common import Terrain,leg_time,load_inputs,load_resources,make_leg
from radio import Position,direct


ROOT=Path(__file__).resolve().parent


@dataclass(frozen=True)
class Phase:
    mission: str
    kind: str
    t0: float
    t1: float
    start: Position
    end: Position

    def at(self,t):
        p=0. if self.t1==self.t0 else (t-self.t0)/(self.t1-self.t0)
        return Position(self.start.lon+(self.end.lon-self.start.lon)*p,
                        self.start.lat+(self.end.lat-self.start.lat)*p,
                        self.start.alt_m+(self.end.alt_m-self.start.alt_m)*p)


def transport_phases(mission,nodes,models,legs):
    m=models[mission['model']]
    nboxes=sum(len(x['boxes']) for x in mission['stops'])
    now=mission['start_s']+m.prep_s+nboxes*m.load_box_s
    phases=[]; prev='O01'
    for next_id,stop in [(x['zone'],x) for x in mission['stops']]+[('O01',None)]:
        leg=legs[prev,next_id]
        a=nodes[prev]; b=nodes[next_id]
        h0=a.ground_m+(30 if prev.startswith('S') else 0)
        h1=b.ground_m+(30 if next_id.startswith('S') else 0)
        p0=Position(a.lon,a.lat,h0)
        p1=Position(a.lon,a.lat,leg.cruise_alt_m)
        p2=Position(b.lon,b.lat,leg.cruise_alt_m)
        p3=Position(b.lon,b.lat,h1)
        for kind,src,dst,duration in [('climb',p0,p1,leg.climb_m/m.climb_mps),
                                      ('cruise',p1,p2,leg.distance_m/m.cruise_mps),
                                      ('descent',p2,p3,leg.descent_m/m.descent_mps)]:
            phases.append(Phase(mission['id'],kind,now,now+duration,src,dst))
            now+=duration
        if stop is not None:
            duration=m.handoff_base_s+len(stop['boxes'])*m.handoff_box_s
            phases.append(Phase(mission['id'],'delivery',now,now+duration,p3,p3))
            now+=duration
        prev=next_id
    if abs(now-mission['return_s'])>1e-4:
        raise ValueError(f"Q2航段时间与提交结果不一致 {mission['id']}: {now} vs {mission['return_s']}")
    return phases


def main():
    nodes,models,boxes=load_inputs(); resources=load_resources(); terrain=Terrain()
    seed=len(sys.argv)>1 and sys.argv[1]=='seed'
    if seed:
        q2=json.loads((ROOT/'结果'/'q3_transport_seed.json').read_text(encoding='utf-8'))['missions']
    else:
        q2=json.loads((ROOT/'结果'/'q2_results.json').read_text(encoding='utf-8'))['merged']['missions']
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    radio=resources.radio
    samples=[]
    for mission in q2:
        for phase in transport_phases(mission,nodes,models,legs):
            n=max(1,int((phase.t1-phase.t0)/12)+1)
            for k in range(n+1):
                t=phase.t0+(phase.t1-phase.t0)*k/n
                pos=phase.at(t)
                d=direct(pos,nodes,terrain,radio)
                samples.append({'mission':mission['id'],'phase':phase.kind,'t':round(t,4),
                                'lon':round(pos.lon,8),'lat':round(pos.lat,8),'alt_m':round(pos.alt_m,4),
                                'direct_margin_db':round(d['margin_db'],4),'clearance_m':round(d['clearance_m'],4),
                                'direct':d['available']})
    blind=[s for s in samples if not s['direct']]
    by_mission={m['id']:sum(s['mission']==m['id'] for s in blind) for m in q2}
    result={'sample_step_max_s':12,'samples':samples,
            'summary':{'sample_count':len(samples),'blind_sample_count':len(blind),
                       'missions_with_blind_samples':{k:v for k,v in by_mission.items() if v}}}
    out=ROOT/'结果'/('q3_seed_direct_diagnostic.json' if seed else 'q3_direct_diagnostic.json')
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(out)
    print(result['summary'])


if __name__=='__main__': main()
