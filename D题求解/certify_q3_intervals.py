# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""保守区间链路检查：以最坏遮挡或可证明无遮挡给出连续时间充分条件。"""
from __future__ import annotations

import argparse
import json
import hashlib
from collections import Counter
from math import ceil,cos,log10,pi,sin,sqrt
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources,make_leg
from diagnose_q3 import transport_phases
from radio import Position,gateway,link_budget
from radio_interval import clear_interval

ROOT=Path(__file__).resolve().parent


def max_distance_m(a,b,terminal):
    # 与 d_common.horizontal_distance_m 同一局部 WGS84 公式。将经纬差的绝对值
    # 和纬度尺度分别取区间上界，再合成距离上界，不依赖“端点距离最大”的近似。
    e2=.0066943799901413165;major=6378137.0
    means=[(p.lat+terminal.lat)/2*pi/180 for p in (a,b)]
    min_abs=0. if means[0]*means[1]<=0 else min(abs(x) for x in means)
    max_abs=max(abs(x) for x in means)
    east_scale=major*cos(min_abs)/sqrt(1-e2*sin(min_abs)**2)
    north_scale=major*(1-e2)/(1-e2*sin(max_abs)**2)**1.5
    dl=max(abs(p.lon-terminal.lon) for p in (a,b))*pi/180
    db=max(abs(p.lat-terminal.lat) for p in (a,b))*pi/180
    dz=max(abs(p.alt_m-terminal.alt_m) for p in (a,b))
    return sqrt((dl*east_scale)**2+(db*north_scale)**2+dz**2)


def guaranteed_margin(a,b,terminal,radio,interface_a,interface_b):
    d=max_distance_m(a,b,terminal)/1000
    fspl=32.45+20*log10(radio['传播参数::f'])+20*log10(d)
    limit=(min(radio[f'{interface_a}::Pt'],radio[f'{interface_b}::Pt'])+
           radio[f'{interface_a}::G']+radio[f'{interface_b}::G']-
           radio['传播参数::Lsys']-radio['接收参数::Psens']-radio['接收参数::M'])
    return limit-fspl-radio['传播参数::Lobs']


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--required-margin-db',type=float,default=0.0,
                        help='要求至少保留的链路预算裕量；可在直连低于该值时计入已在位中继备份')
    parser.add_argument('--solution',type=Path,default=ROOT/'结果'/'q3_solution.json')
    args=parser.parse_args()
    required=args.required_margin_db
    if required<0:raise ValueError('安全裕量必须非负')
    data=json.loads(args.solution.read_text(encoding='utf-8'))
    nodes,models,_=load_inputs();terrain=Terrain();radio=load_resources().radio
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    gate=gateway(nodes,radio);relay=data['relay_sorties']
    static_backhaul={r['id']:link_budget(Position(r['lon'],r['lat'],r['alt_m']),gate,terrain,radio,
                                         '中继回传端','固定网关 G01','exact')['margin_db'] for r in relay}
    def best_margin(phase,t0,t1):
        a=phase.at(t0);b=phase.at(t1)
        direct_margin=guaranteed_margin(a,b,gate,radio,'运输无人机','固定网关 G01')
        if direct_margin<required and direct_margin+radio['传播参数::Lobs']>=required and clear_interval(a,b,gate,terrain):
            direct_margin+=radio['传播参数::Lobs']
        options=[('direct',direct_margin)]
        if direct_margin<required:
            for r in relay:
                if r['ready_s']-1e-9<=t0 and t1<=r['service_end_s']+1e-9:
                    h=Position(r['lon'],r['lat'],r['alt_m'])
                    access=guaranteed_margin(a,b,h,radio,'运输无人机','中继接入端')
                    if access<required and access+radio['传播参数::Lobs']>=required and clear_interval(a,b,h,terrain):
                        access+=radio['传播参数::Lobs']
                    options.append((r['id'],min(access,static_backhaul[r['id']])))
        return max(options,key=lambda x:x[1])

    counts=Counter();unresolved=[];lowest_certified=float('inf');limiting_interval=None
    def point_margin(phase,t):
        p=phase.at(t)
        available=[link_budget(p,gate,terrain,radio,'运输无人机','固定网关 G01','exact')['margin_db']]
        for r in relay:
            if r['ready_s']<=t<=r['service_end_s']:
                access=link_budget(p,Position(r['lon'],r['lat'],r['alt_m']),terrain,radio,
                                   '运输无人机','中继接入端','exact')['margin_db']
                available.append(min(access,static_backhaul[r['id']]))
        return max(available)
    def record_min(phase,t0,t1,name,margin):
        nonlocal lowest_certified,limiting_interval
        if margin<lowest_certified:
            lowest_certified=margin
            limiting_interval={'mission':phase.mission,'phase':phase.kind,
                               'start_s':t0,'end_s':t1,'path':name,'margin_db':margin}
    for m in data['transport_missions']:
        for phase in transport_phases(m,nodes,models,legs):
            n=max(1,ceil((phase.t1-phase.t0)/1))
            times={phase.t0+(phase.t1-phase.t0)*k/n for k in range(n+1)}
            for r in relay:
                for t in (r['ready_s'],r['service_end_s']):
                    if phase.t0<t<phase.t1:times.add(t)
            ts=sorted(times)
            for t0,t1 in zip(ts,ts[1:]):
                name,margin=best_margin(phase,t0,t1)
                counts['intervals']+=1
                if margin>=required:
                    counts['certified']+=1
                    record_min(phase,t0,t1,name,margin)
                else:unresolved.append((phase,t0,t1))
    initial_unresolved=len(unresolved)
    # 模态切换落在粗网格内部时，对该区间二分。每个叶区间单独得到连续保证。
    failures=[]
    for phase,t0,t1 in unresolved:
        stack=[(t0,t1,0)]
        while stack:
            u,v,depth=stack.pop()
            name,margin=best_margin(phase,u,v)
            counts['refinement_checks']+=1
            if margin>=required:
                counts['refined_certified_leaves']+=1
                record_min(phase,u,v,name,margin)
            elif point_margin(phase,(u+v)/2)<required-1e-8:
                # 单个实际点值不达标已足以否定全区间，不需穷举二分全部叶子。
                counts['point_counterexamples']+=1
                counts['uncertified_leaves']+=1
                if len(failures)<30:
                    failures.append((phase.mission,phase.kind,round((u+v)/2,9),'point_counterexample'))
            elif depth<14 and v-u>1e-4:
                mid=(u+v)/2
                stack.extend(((u,mid,depth+1),(mid,v,depth+1)))
            else:
                if len(failures)<30:
                    failures.append((phase.mission,phase.kind,round(u,7),round(v,7),name,round(margin,5)))
                counts['uncertified_leaves']+=1
    out={'method':'每个约1秒时间段对三维距离取分量保守上界；若逐格扫掠证明无遮挡则不加遮挡损耗，否则按全程遮挡损耗计；静态回传逐格精确判别',
         'required_margin_db':required,
         'source_sha256':hashlib.sha256(args.solution.read_bytes()).hexdigest(),
         'backup_rule':'直连低于目标裕量时检查已在位中继；名义通信状态仍按题面直连优先记录',
         'counts':counts,'initial_uncertain_intervals':initial_unresolved,
         'certified_all_intervals':counts['uncertified_leaves']==0,
         'uncertain_examples':failures,'min_certified_margin_db':lowest_certified,
         'limiting_interval':limiting_interval}
    suffix='interval_certificate' if required==0 else f'margin_certificate_{required:g}db'
    if args.solution.stem!='q3_solution':suffix+=f'_{args.solution.stem}'
    (ROOT/'结果'/f'q3_{suffix}.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(out)
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
