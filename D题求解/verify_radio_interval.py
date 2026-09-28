# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""移动视线连续无遮挡判别的人工算例与随机密采样反证测试。"""
from __future__ import annotations

import random

import numpy as np

from d_common import Terrain
from radio import Position,loss_and_clearance
from radio_interval import clear_interval


def point(x,y,z):
    return Position(x,10-y,z)


def make_terrain():
    t=Terrain.__new__(Terrain)
    t.a=np.zeros((8,8),dtype=np.float32)
    t.x0=.5;t.y0=9.5;t.dx=t.dy=1.;t.width=t.height=8
    t.nodata=-32767.;t.pixel_is_point=True
    return t


def main():
    terrain=make_terrain();terminal=point(.3,.3,10)
    a=point(6.7,6.6,10);b=point(6.7,6.7,10)
    assert clear_interval(a,b,terminal,terrain)
    terrain.a[3,3]=20
    assert not clear_interval(a,b,terminal,terrain)
    terrain.a[3,3]=0
    # 网格角点擦边的高像元须阻断保守证书。
    terrain.a[0,1]=20
    assert not clear_interval(point(2.8,2.8,10),point(2.8,2.8,10),
                              point(.2,.2,10),terrain)
    terrain.a[0,1]=0
    rng=random.Random(20260924)
    tests=0;certified=0
    for _ in range(200):
        terrain.a=np.asarray([[rng.choice((0.,0.,0.,5.,12.,20.)) for _ in range(8)] for _ in range(8)],dtype=np.float32)
        gx,gy=rng.uniform(.2,6.8),rng.uniform(.2,6.8)
        x0,y0=rng.uniform(.2,6.8),rng.uniform(.2,6.8)
        x1,y1=x0+rng.uniform(-.5,.5),y0+rng.uniform(-.5,.5)
        x1=max(.2,min(6.8,x1));y1=max(.2,min(6.8,y1))
        base=point(gx,gy,rng.uniform(8,25))
        p0=point(x0,y0,rng.uniform(8,25));p1=point(x1,y1,rng.uniform(8,25))
        proof=clear_interval(p0,p1,base,terrain)
        tests+=1;certified+=int(proof)
        if proof:
            for k in range(101):
                u=k/100
                p=point(x0+(x1-x0)*u,y0+(y1-y0)*u,p0.alt_m+(p1.alt_m-p0.alt_m)*u)
                _,clearance,_=loss_and_clearance(base,p,terrain,{'传播参数::f':2400,'传播参数::Lobs':10},'exact')
                if clearance<0:raise AssertionError(('false_clear_certificate',tests,u,clearance))
    print('manual_cases=PASS random_cases',tests,'certified',certified,'sampled_counterexamples=0')


if __name__=='__main__':main()
