# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""直连优先的通信记录：区间充分条件与显式数值切换边界。

连续通信存在性由独立的区间检查器核验。本程序还核验表中所指派的路径，
并为无法用单一状态描述的切换邻域记录数值误差，不将采样中点当作精确切换。
"""
from __future__ import annotations

import hashlib
import json
from math import ceil, cos, floor, log10, pi, sin, sqrt
from pathlib import Path

import numpy as np

from certify_q3_intervals import guaranteed_margin
from d_common import Terrain, load_inputs, load_resources, make_leg
from diagnose_q3 import transport_phases
from radio import Position, direct, gateway, link_budget, relay_path
from radio_interval import clear_interval

ROOT = Path(__file__).resolve().parent
TIME_TOL = 1e-7
LABELS = {'climb': '爬升', 'cruise': '巡航', 'descent': '下降', 'delivery': '交接'}


def solution_hash(data):
    payload = {k: data[k] for k in ('transport_missions', 'relay_sorties')}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def schedule_hash(schedule):
    payload={k:schedule[k] for k in ('solution_sha256','records','boundary_brackets')}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def min_distance_m(a, b, terminal):
    """移动线段端点包围盒到固定端点距离的下界，与局部 WGS84 公式一致。"""
    def amin(x, y):
        return 0.0 if x*y <= 0 else min(abs(x), abs(y))
    e2 = .0066943799901413165
    means = [(p.lat+terminal.lat)*pi/360 for p in (a,b)]
    lo = amin(*means); hi = max(map(abs,means))
    east = 6378137*cos(hi)/sqrt(1-e2*sin(hi)**2)
    north = 6378137*(1-e2)/(1-e2*sin(lo)**2)**1.5
    dx = amin(a.lon-terminal.lon,b.lon-terminal.lon)*pi/180*east
    dy = amin(a.lat-terminal.lat,b.lat-terminal.lat)*pi/180*north
    dz = amin(a.alt_m-terminal.alt_m,b.alt_m-terminal.alt_m)
    return sqrt(dx*dx+dy*dy+dz*dz)


def blocked_interval(a, b, terminal, terrain):
    """固定视线比例处全时间在地形下是持续遮挡的充分条件。

    在中时刻各穿格子段内部寻找见证点；再对该见证点扫过的矩形取最低地形、
    最高视线高度。避免把某个时刻的遮挡误当作整段遮挡。
    """
    gx,gy = terrain.pixel(terminal.lon,terminal.lat)
    ax,ay = terrain.pixel(a.lon,a.lat); bx,by = terrain.pixel(b.lon,b.lat)
    mx,my,mz = (ax+bx)/2,(ay+by)/2,(a.alt_m+b.alt_m)/2
    cuts = [0.,1.]
    for g,m in ((gx,mx),(gy,my)):
        if abs(m-g)>1e-12:
            cuts.extend((k-g)/(m-g) for k in range(floor(min(g,m))+1,ceil(max(g,m))))
    cuts = np.array(sorted(set(cuts)))
    # 每个像元靠近两端和中点都试；靠内取点以避开仅擦边的假见证。
    factors=(1e-10,1e-8,1e-6,1e-4,.5,1-1e-4,1-1e-6,1-1e-8,1-1e-10)
    ss = np.concatenate([cuts[:-1]+(cuts[1:]-cuts[:-1])*f for f in factors])
    cx = np.floor(gx+ss*(mx-gx)).astype(int)
    cy = np.floor(gy+ss*(my-gy)).astype(int)
    heights = terminal.alt_m+ss*(mz-terminal.alt_m)
    deficit = heights-terrain.a[cy,cx]
    for index in np.argsort(deficit)[:96]:
        if deficit[index]>=0:break
        s=float(ss[index])
        xs=[gx+s*(x-gx) for x in (ax,bx)]
        ys=[gy+s*(y-gy) for y in (ay,by)]
        c0,c1=floor(min(xs)-1e-10),floor(max(xs)+1e-10)
        r0,r1=floor(min(ys)-1e-10),floor(max(ys)+1e-10)
        if c0<0 or r0<0 or c1>=terrain.width or r1>=terrain.height:continue
        ground=terrain.a[r0:r1+1,c0:c1+1]
        if np.any(~np.isfinite(ground)) or np.any(ground<=terrain.nodata):continue
        zmax=terminal.alt_m+s*(max(a.alt_m,b.alt_m)-terminal.alt_m)
        if zmax<float(np.min(ground))-1e-10:return True
    return False


class CommunicationModel:
    def __init__(self,data):
        self.data=data
        self.nodes,self.models,_=load_inputs()
        self.terrain=Terrain();self.radio=load_resources().radio
        self.gate=gateway(self.nodes,self.radio)
        self.legs={(a,b):make_leg(self.terrain,self.nodes[a],self.nodes[b])
                   for a in self.nodes for b in self.nodes if a!=b}
        self.relays={r['id']:r for r in data['relay_sorties']}
        self.sites={rid:Position(r['lon'],r['lat'],r['alt_m']) for rid,r in self.relays.items()}
        self.backhaul={rid:link_budget(p,self.gate,self.terrain,self.radio,
                                       '中继回传端','固定网关 G01','exact')['margin_db']
                       for rid,p in self.sites.items()}

    def available_interval(self,a,b,terminal,ia,ib):
        lower=guaranteed_margin(a,b,terminal,self.radio,ia,ib)
        if lower>=0:return True
        return lower+self.radio['传播参数::Lobs']>=0 and clear_interval(a,b,terminal,self.terrain)

    def direct_unavailable_interval(self,a,b):
        distance=min_distance_m(a,b,self.gate)/1000
        if distance<=0:return False
        r=self.radio
        limit=(min(r['运输无人机::Pt'],r['固定网关 G01::Pt'])+
               r['运输无人机::G']+r['固定网关 G01::G']-r['传播参数::Lsys']-
               r['接收参数::Psens']-r['接收参数::M'])
        upper=limit-(32.45+20*log10(r['传播参数::f'])+20*log10(distance))
        if upper < -1e-9:return True
        return upper-r['传播参数::Lobs'] < -1e-9 and blocked_interval(a,b,self.gate,self.terrain)

    def point_state(self,phase,t):
        p=phase.at(t)
        if direct(p,self.nodes,self.terrain,self.radio,'exact')['available']:
            return ('直连','')
        for rid,r in self.relays.items():
            if r['ready_s']<=t<=r['service_end_s'] and relay_path(
                    p,self.sites[rid],self.nodes,self.terrain,self.radio,'exact')['available']:
                return ('中继',rid)
        raise RuntimeError(f'通信中断: {phase.mission}, {phase.kind}, {t:.12f}')

    def certify_state(self,phase,t0,t1,state):
        a,b=phase.at(t0),phase.at(t1)
        if state[0]=='直连':
            return self.available_interval(a,b,self.gate,'运输无人机','固定网关 G01')
        if not self.direct_unavailable_interval(a,b):return False
        rid=state[1];r=self.relays[rid]
        return (r['ready_s']<=t0 and t1<=r['service_end_s'] and self.backhaul[rid]>=0 and
                self.available_interval(a,b,self.sites[rid],'运输无人机','中继接入端'))


def build(data):
    model=CommunicationModel(data);records=[];boundaries=[];counts={'certified_leaves':0,'boundary_leaves':0}
    for mission in data['transport_missions']:
        for phase_index,phase in enumerate(transport_phases(mission,model.nodes,model.models,model.legs)):
            n=max(1,ceil(phase.t1-phase.t0))
            cuts={phase.t0+(phase.t1-phase.t0)*k/n for k in range(n+1)}
            cuts.update(t for r in model.relays.values() for t in (r['ready_s'],r['service_end_s'])
                        if phase.t0<t<phase.t1)
            leaves=[]
            phase_boundary_count=0
            def divide(u,v):
                nonlocal phase_boundary_count
                state=model.point_state(phase,(u+v)/2)
                if model.certify_state(phase,u,v,state):
                    counts['certified_leaves']+=1;leaves.append((u,v,state));return
                if v-u<=TIME_TOL:
                    phase_boundary_count+=1
                    if phase_boundary_count>16:
                        raise RuntimeError(f'非孤立切换区间需改进证明: {phase.mission} {phase_index} {u} {v} {state}')
                    # 有限精度边界不能写成已证明的单状态区间。
                    counts['boundary_leaves']+=1
                    boundaries.append({'mission':mission['id'],'phase_index':phase_index,
                                       'start_s':u,'end_s':v,'midpoint_state':state})
                    leaves.append((u,v,state));return
                mid=(u+v)/2
                divide(u,mid);divide(mid,v)
            ts=sorted(cuts)
            for u,v in zip(ts,ts[1:]):divide(u,v)
            merged=[]
            for u,v,state in leaves:
                if merged and merged[-1][2]==state:merged[-1]=(merged[-1][0],v,state)
                else:merged.append((u,v,state))
            records.extend({'mission':mission['id'],'phase':phase.kind,'phase_index':phase_index,
                            'start_s':u,'end_s':v,'mode':state[0],'relay_id':state[1]}
                           for u,v,state in merged)
        print('communication',mission['id'],'records',len(records),'boundary_leaves',len(boundaries),flush=True)
    return {'solution_sha256':solution_hash(data),'time_tolerance_s':TIME_TOL,
            'boundary_rule':'数值切换边界误差不超过记录的微小区间；精确边界点按原题直连优先规则实时判定。',
            'counts':counts,'records':records,'boundary_brackets':boundaries}


def main():
    p=ROOT/'结果'/'q3_solution.json'
    data=json.loads(p.read_text(encoding='utf-8'))
    result=build(data)
    (ROOT/'结果'/'q3_communication_schedule.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('done',result['counts'],'records',len(result['records']))


if __name__=='__main__':main()
