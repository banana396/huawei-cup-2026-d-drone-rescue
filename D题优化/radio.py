# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""第三问通信几何与链路预算。距离按三维米、损耗公式按公里。"""
from __future__ import annotations

from dataclasses import dataclass
from math import log10,sqrt

import numpy as np

from d_common import Node,horizontal_distance_m


@dataclass(frozen=True)
class Position:
    lon: float
    lat: float
    alt_m: float


def gateway(nodes, radio):
    n=nodes['O01']
    return Position(n.lon,n.lat,n.ground_m+radio['固定网关 G01::hG'])


def loss_and_clearance(a: Position,b: Position,terrain,radio,step_pixels=.4):
    x1,y1=terrain.pixel(a.lon,a.lat); x2,y2=terrain.pixel(b.lon,b.lat)
    if step_pixels=='exact':
        # 栅格高程为像元常数；沿视线按每个网格边界切段，线性海拔在端点取极小值。
        cuts=[0.,1.]
        if x2!=x1:
            cuts.extend((k-x1)/(x2-x1) for k in range(int(np.floor(min(x1,x2)))+1,
                                                    int(np.ceil(max(x1,x2)))))
        if y2!=y1:
            cuts.extend((k-y1)/(y2-y1) for k in range(int(np.floor(min(y1,y2)))+1,
                                                    int(np.ceil(max(y1,y2)))))
        t=np.array(sorted(set(v for v in cuts if 0<=v<=1)))
        mids=(t[:-1]+t[1:])/2
        cols=np.floor(x1+(x2-x1)*mids).astype(int)
        rows=np.floor(y1+(y2-y1)*mids).astype(int)
    else:
        n=max(2,int(max(abs(x2-x1),abs(y2-y1))/step_pixels)+2)
        t=np.linspace(0,1,n)
        cols=np.floor(x1+(x2-x1)*t).astype(int)
        rows=np.floor(y1+(y2-y1)*t).astype(int)
    if np.any(cols<0) or np.any(cols>=terrain.width) or np.any(rows<0) or np.any(rows>=terrain.height):
        raise ValueError('通信视线越出DEM范围')
    ground=terrain.a[rows,cols]
    if np.any(~np.isfinite(ground)) or np.any(ground<=terrain.nodata):
        raise ValueError('通信视线经过无效DEM像元')
    if step_pixels=='exact':
        alt_left=a.alt_m+(b.alt_m-a.alt_m)*t[:-1]
        alt_right=a.alt_m+(b.alt_m-a.alt_m)*t[1:]
        clearance=float(np.min(np.minimum(alt_left,alt_right)-ground))
        # 恰好擦过网格线/角点的侧邻像元也纳入，形成保守 supercover。
        xs=x1+(x2-x1)*t;ys=y1+(y2-y1)*t
        cx=np.floor(xs).astype(int);cy=np.floor(ys).astype(int)
        xr=np.rint(xs).astype(int);yr=np.rint(ys).astype(int)
        onx=np.abs(xs-xr)<1e-9;ony=np.abs(ys-yr)<1e-9
        c0=np.where(onx,xr,cx);c1=np.where(onx,xr-1,cx)
        r0=np.where(ony,yr,cy);r1=np.where(ony,yr-1,cy)
        at_alt=a.alt_m+(b.alt_m-a.alt_m)*t
        for cc,rr in ((c0,r0),(c0,r1),(c1,r0),(c1,r1)):
            if np.any(cc<0) or np.any(cc>=terrain.width) or np.any(rr<0) or np.any(rr>=terrain.height):
                raise ValueError('通信视线接触DEM范围外')
            g=terrain.a[rr,cc]
            if np.any(~np.isfinite(g)) or np.any(g<=terrain.nodata):
                raise ValueError('通信视线接触无效DEM像元')
            clearance=min(clearance,float(np.min(at_alt-g)))
    else:
        line_alt=a.alt_m+(b.alt_m-a.alt_m)*t
        clearance=float(np.min(line_alt-ground))
    h=horizontal_distance_m(Node('',a.lon,a.lat,0),Node('',b.lon,b.lat,0))
    distance_km=sqrt(h*h+(b.alt_m-a.alt_m)**2)/1000
    if distance_km<=0: raise ValueError('两个端点重合')
    fspl=32.45+20*log10(radio['传播参数::f'])+20*log10(distance_km)
    obstructed=clearance<0
    return fspl+(radio['传播参数::Lobs'] if obstructed else 0),clearance,distance_km


def link_budget(a: Position,b: Position,terrain,radio,interface_a,interface_b,step_pixels=.4):
    loss,clearance,distance=loss_and_clearance(a,b,terrain,radio,step_pixels)
    threshold=radio['接收参数::Psens']+radio['接收参数::M']
    system=radio['传播参数::Lsys']
    gt_a=radio[f'{interface_a}::G']; gt_b=radio[f'{interface_b}::G']
    forward=radio[f'{interface_a}::Pt']+gt_a+gt_b-system-threshold
    backward=radio[f'{interface_b}::Pt']+gt_b+gt_a-system-threshold
    margin=min(forward,backward)-loss
    return {'available':margin>=-1e-9,'margin_db':margin,'clearance_m':clearance,
            'distance_km':distance,'path_loss_db':loss,'limit_db':min(forward,backward)}


def direct(pos, nodes,terrain,radio,step_pixels=.4):
    return link_budget(pos,gateway(nodes,radio),terrain,radio,'运输无人机','固定网关 G01',step_pixels)


def relay_path(pos,hover,nodes,terrain,radio,step_pixels=.4):
    access=link_budget(pos,hover,terrain,radio,'运输无人机','中继接入端',step_pixels)
    backhaul=link_budget(hover,gateway(nodes,radio),terrain,radio,'中继回传端','固定网关 G01',step_pixels)
    return {'available':access['available'] and backhaul['available'],
            'margin_db':min(access['margin_db'],backhaul['margin_db']),
            'access':access,'backhaul':backhaul}
