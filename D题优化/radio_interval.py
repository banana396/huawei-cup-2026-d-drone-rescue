# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""固定终端到线性移动终端的 DSM 全时间无遮挡充分判别。"""
from __future__ import annotations

from math import ceil,floor


def _ground_max(terrain,rows,cols):
    if min(rows)<0 or max(rows)>=terrain.height or min(cols)<0 or max(cols)>=terrain.width:
        raise ValueError('时空视线扫过DEM范围外')
    vals=[float(terrain.a[r,c]) for r in rows for c in cols]
    if any(v<=terrain.nodata for v in vals):raise ValueError('时空视线扫过无效DEM')
    return max(vals)


def _span(lo,hi):
    start=floor(lo)
    end=floor(hi)
    if abs(lo-round(lo))<1e-9:start=round(lo)-1
    if abs(hi-round(hi))<1e-9:end=round(hi)
    return range(start,end+1)


def _point_cells(x,y):
    cols=list(_span(x,x));rows=list(_span(y,y))
    return rows,cols


def clear_interval(a,b,terminal,terrain):
    """若返回 True，则连续时间内所有视线段都在触及的 DSM 像元之上。"""
    gx,gy=terrain.pixel(terminal.lon,terminal.lat)
    x0,y0=terrain.pixel(a.lon,a.lat)
    x1,y1=terrain.pixel(b.lon,b.lat)
    gz=terminal.alt_m;z0=a.alt_m;z1=b.alt_m
    rows,cols=_point_cells(gx,gy)
    if gz<=_ground_max(terrain,rows,cols):return False
    cuts={0.,1.}
    for u,v in ((x0,x1),(y0,y1)):
        if abs(v-u)>1e-12:
            for k in range(floor(min(u,v))+1,ceil(max(u,v))):
                t=(k-u)/(v-u)
                if 0<t<1:cuts.add(t)
    times=sorted(cuts)
    for u,v in zip(times,times[1:]):
        xa=x0+(x1-x0)*u;xb=x0+(x1-x0)*v
        ya=y0+(y1-y0)*u;yb=y0+(y1-y0)*v
        za=z0+(z1-z0)*u;zb=z0+(z1-z0)*v
        # 终点沿该子区间至多在一个像元内部运动；端点若贴边也纳入相邻格。
        endpoint_rows=list(_span(min(ya,yb),max(ya,yb)))
        endpoint_cols=list(_span(min(xa,xb),max(xa,xb)))
        if min(za,zb)<=_ground_max(terrain,endpoint_rows,endpoint_cols):return False
        xm=(xa+xb)/2;ym=(ya+yb)/2
        for k in range(ceil(min(gx,xm)),floor(max(gx,xm))+1):
            if abs(xa-gx)<1e-12 or abs(xb-gx)<1e-12:return False
            sa=(k-gx)/(xa-gx);sb=(k-gx)/(xb-gx)
            if not (-1e-9<=sa<=1+1e-9 and -1e-9<=sb<=1+1e-9):continue
            yca=gy+sa*(ya-gy);ycb=gy+sb*(yb-gy)
            zca=gz+sa*(za-gz);zcb=gz+sb*(zb-gz)
            rows=list(_span(min(yca,ycb),max(yca,ycb)))
            if min(zca,zcb)<=_ground_max(terrain,rows,[k-1,k]):return False
        for k in range(ceil(min(gy,ym)),floor(max(gy,ym))+1):
            if abs(ya-gy)<1e-12 or abs(yb-gy)<1e-12:return False
            sa=(k-gy)/(ya-gy);sb=(k-gy)/(yb-gy)
            if not (-1e-9<=sa<=1+1e-9 and -1e-9<=sb<=1+1e-9):continue
            xca=gx+sa*(xa-gx);xcb=gx+sb*(xb-gx)
            zca=gz+sa*(za-gz);zcb=gz+sb*(zb-gz)
            cols=list(_span(min(xca,xcb),max(xca,xcb)))
            if min(zca,zcb)<=_ground_max(terrain,[k-1,k],cols):return False
    return True
