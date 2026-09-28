# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""DEM 几何校验：用密集采样和人工构造网格检验公共穿格算法。"""
from __future__ import annotations

from math import asin, cos, pi, sin, sqrt
from pathlib import Path

import numpy as np
from PIL import Image

from d_common import DEM, Node, Terrain, horizontal_distance_m, load_inputs, make_leg


def reference_max(array, tag, a, b):
    """独立密集采样参考，GeoTIFF Point tiepoint 对应第0像元中心。"""
    scale=tag[33550]; tie=tag[33922]
    x1=(a.lon-tie[3])/scale[0]+0.5
    y1=(tie[4]-a.lat)/scale[1]+0.5
    x2=(b.lon-tie[3])/scale[0]+0.5
    y2=(tie[4]-b.lat)/scale[1]+0.5
    n=int(max(abs(x2-x1),abs(y2-y1))*30)+2
    t=np.linspace(0,1,n)
    cols=np.floor(x1+(x2-x1)*t).astype(int)
    rows=np.floor(y1+(y2-y1)*t).astype(int)
    if min(cols)<0 or max(cols)>=array.shape[1] or min(rows)<0 or max(rows)>=array.shape[0]:
        raise AssertionError('采样出DEM范围')
    vals=array[rows,cols]
    if not np.isfinite(vals).all() or np.any(vals<=-32767): raise AssertionError('采样遇到NoData')
    return float(vals.max())


def toy_node(name,x,y):
    return Node(name,float(x),float(6-y),0)


def toy_tests():
    t=Terrain.__new__(Terrain)
    t.a=np.zeros((4,4),dtype=np.float32)
    t.x0=.5; t.y0=5.5; t.dx=1.; t.dy=1.
    t.width=t.height=4; t.nodata=-32767.; t.pixel_is_point=True
    assert t.pixel(.5,5.5)==(.5,.5)
    assert t.sample(.5,5.5)==0
    t.a[1,1]=90
    assert t.line_max(toy_node('A',.1,.1),toy_node('B',2.8,2.8))==90
    t.a[1,1]=0; t.a[1,0]=80
    assert t.line_max(toy_node('A',1,.2),toy_node('B',1,2.8))==80
    t.a[1,0]=0; t.a[0,1]=70
    assert t.line_max(toy_node('A',.2,.2),toy_node('B',2.8,2.8))==70
    t.a[0,1]=-32767
    try: t.line_max(toy_node('A',.2,.2),toy_node('B',2.8,2.8))
    except ValueError: pass
    else: raise AssertionError('未检测到NoData')


def main():
    toy_tests()
    im=Image.open(DEM)
    array=np.asarray(im)
    terrain=Terrain()
    assert terrain.pixel_is_point
    assert terrain.pixel(terrain.x0,terrain.y0)==(.5,.5)
    nodes,_,_=load_inputs()
    ids=sorted(nodes)
    peak_diffs=[]; max_distance_diff=0.; node_samples=[]
    for i,a_id in enumerate(ids):
        a=nodes[a_id]
        node_samples.append((a_id,round(a.ground_m,3),round(terrain.sample(a.lon,a.lat),3)))
        for b_id in ids[i+1:]:
            b=nodes[b_id]
            exact=terrain.line_max(a,b)
            reverse=terrain.line_max(b,a)
            if exact!=reverse: raise AssertionError(f'正反向像元集合不一致: {a_id}-{b_id}')
            dense=reference_max(array,im.tag_v2,a,b)
            peak_diffs.append((abs(exact-dense),a_id,b_id,exact,dense))
            # 距离与球面大圆结果的差异只报告量级，不作为正确性判定。
            p1,p2=a.lat*pi/180,b.lat*pi/180
            dl=(b.lon-a.lon)*pi/180
            h=sin((p2-p1)/2)**2+cos(p1)*cos(p2)*sin(dl/2)**2
            sphere=2*6371008.8*asin(sqrt(h))
            max_distance_diff=max(max_distance_diff,abs(horizontal_distance_m(a,b)-sphere))
    print('toy_tests=PASS directed_symmetry=PASS node_pairs=',len(peak_diffs))
    print('dense_reference_max_difference_m=',max(x[0] for x in peak_diffs))
    print('max_distance_difference_vs_sphere_m=',round(max_distance_diff,4))
    print('node_heights_id_excel_dsm=',node_samples)
    underestimate=[x for x in peak_diffs if x[4]>x[3]+1e-6]
    corner_touches=[x for x in peak_diffs if x[3]>x[4]+1e-6]
    print('dense_reference_exceeds_grid_max=',underestimate[:10])
    print('conservative_boundary_contact_cases=',corner_touches[:10])
    if underestimate: raise SystemExit(1)


if __name__=='__main__': main()
