# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""D题公共数据与物理计算。Codex AI 辅助编写；正式提交前由队员核验并补全工具型号、机构和发布日期。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from math import ceil, cos, floor, pi, sqrt
from pathlib import Path

import numpy as np
import openpyxl
from PIL import Image


ROOT = Path(__file__).resolve().parent.parent / "2026年中国研究生数学建模竞赛赛题" / "D题"
DATA = ROOT / "数据" / "无人机应急物资运输基础数据"
DEM = next(ROOT.rglob("*.tif"))
G = 9.80665  # m/s^2，建模常数，题面未指定数值


@dataclass(frozen=True)
class Node:
    id: str
    lon: float
    lat: float
    ground_m: float  # 起降高度以节点表为准；地形遮挡用DSM


@dataclass(frozen=True)
class Box:
    id: str
    zone: str
    kind: str
    kg: float
    m3: float
    first: bool
    first_deadline_s: float | None
    expected_s: float
    priority: float


@dataclass(frozen=True)
class Model:
    id: str
    empty_kg: float
    max_kg: float
    max_m3: float
    cruise_mps: float
    range_empty_m: float
    range_full_m: float
    energy_kwh: float
    reserve: float
    prep_s: float
    load_box_s: float
    handoff_base_s: float
    handoff_box_s: float
    climb_mps: float
    descent_mps: float
    climb_eta: float


@dataclass(frozen=True)
class Leg:
    src: str
    dst: str
    distance_m: float
    cruise_alt_m: float
    climb_m: float
    descent_m: float


@dataclass(frozen=True)
class RelayModel:
    id: str
    takeoff_kg: float
    cruise_mps: float
    cruise_kw: float
    energy_kwh: float
    reserve: float
    prep_s: float
    link_setup_s: float
    turnaround_s: float
    climb_mps: float
    descent_mps: float
    climb_eta: float
    hover_kw: float
    comm_kw: float
    max_agl_m: float


@dataclass(frozen=True)
class Resources:
    transport_craft: Mapping[str, str]
    transport_batteries: Mapping[str, tuple[int, float]]
    relay_craft: Mapping[str, str]
    relay_components: Mapping[str, tuple[int, float]]
    relay_models: Mapping[str, RelayModel]
    radio: Mapping[str, float]


def _sheet(filename: str, index: int = 0):
    return openpyxl.load_workbook(DATA / filename, read_only=True, data_only=True).worksheets[index]


def load_inputs():
    s = _sheet("调度中心与服务区.xlsx")
    rows = list(s.values)
    nodes = {"O01": Node("O01", float(rows[2][2]), float(rows[2][3]), float(rows[2][4]))}
    for r in rows[6:]:
        if isinstance(r[0], str) and r[0].startswith("S"):
            nodes[r[0]] = Node(r[0], float(r[2]), float(r[3]), float(r[4]))
    s = _sheet("运输无人机数据.xlsx")
    models = {}
    for r in list(s.values)[2:5]:
        models[r[0]] = Model(r[0], float(r[2]), float(r[3]), float(r[4]),
                             float(r[5]), float(r[6]), float(r[7]), float(r[8]),
                             float(r[9])/100, float(r[10]), float(r[11]),
                             float(r[12]), float(r[13]), float(r[14]),
                             float(r[15]), float(r[16]))
    boxes = {}
    for r in list(_sheet("物资需求与配送时限.xlsx", 1).values)[1:]:
        if not r[0]: continue
        b = Box(str(r[0]), str(r[1]), str(r[2]), float(r[3]), float(r[4]),
                r[5] == "是", float(r[6]) if r[6] is not None else None,
                float(r[7]), float(r[8]))
        if b.id in boxes: raise ValueError(f"重复货箱编号: {b.id}")
        boxes[b.id] = b
    return nodes, models, boxes


def load_resources():
    transport=list(_sheet("运输无人机数据.xlsx").values)
    craft={str(r[0]):str(r[1]) for r in transport[8:16] if r[0]}
    batteries={str(r[0]):(int(r[1]),float(r[2])) for r in transport[19:22] if r[0]}
    relay=list(_sheet("中继无人机数据.xlsx").values)
    r=relay[2]
    relay_models={str(r[0]):RelayModel(str(r[0]),float(r[4]),float(r[5]),float(r[6]),
                                     float(r[7]),float(r[8])/100,float(r[9]),float(r[10]),
                                     float(r[11]),float(r[12]),float(r[13]),float(r[14]),
                                     float(r[16]),float(r[17]),float(r[18]))}
    relay_craft={str(r[0]):str(r[1]) for r in relay[6:8] if r[0]}
    relay_components={str(r[0]):(int(r[1]),float(r[2])) for r in relay[11:12] if r[0]}
    radio={f'{r[0]}::{r[3]}':float(r[4]) for r in list(_sheet("通信链路参数.xlsx").values)[2:] if r[0] and r[3] and isinstance(r[4],(int,float))}
    if len(craft)!=8 or set(batteries)!={"A","B","C"} or len(relay_craft)!=2 or sum(v[0] for v in relay_components.values())!=6:
        raise ValueError('设备或能源资源清单与题面标准场景不符')
    return Resources(craft,batteries,relay_craft,relay_components,relay_models,radio)


def charging_time_s(soc: float, full_s: float):
    if not (0 <= soc <= 1): raise ValueError('SOC超出[0,1]')
    if soc < .90: return full_s*(.65*(.90-soc)/.90+.35)
    return full_s*.35*(1-soc)/.10


class Terrain:
    def __init__(self):
        im = Image.open(DEM)
        self.a = np.array(im, dtype=np.float32)
        scale = im.tag_v2[33550]
        tie = im.tag_v2[33922]
        geokeys = im.tag_v2[34735]
        entries = {geokeys[i]: geokeys[i+3] for i in range(4, len(geokeys), 4)}
        self.pixel_is_point = entries.get(1025, 1) == 2
        self.x0, self.y0 = float(tie[3]), float(tie[4])
        self.dx, self.dy = float(scale[0]), float(scale[1])
        self.height, self.width = self.a.shape
        self.nodata = -32767.0

    def pixel(self, lon, lat):
        offset = 0.5 if self.pixel_is_point else 0.0
        return (lon-self.x0)/self.dx+offset, (self.y0-lat)/self.dy+offset

    def sample(self, lon, lat):
        x,y = self.pixel(lon,lat)
        col,row = floor(x),floor(y)
        if not (0 <= col < self.width and 0 <= row < self.height):
            raise ValueError(f"DEM 范围外: {lon},{lat}")
        h = float(self.a[row,col])
        if h <= self.nodata: raise ValueError(f"DEM 无效像元: {lon},{lat}")
        return h

    def line_max(self, a: Node, b: Node):
        """网格边界分段取中点；穿过角点时连邻格一并纳入。"""
        x1,y1 = self.pixel(a.lon,a.lat)
        x2,y2 = self.pixel(b.lon,b.lat)
        cuts = [0.0,1.0]
        if x2 != x1:
            for k in range(floor(min(x1,x2))+1,ceil(max(x1,x2))):
                t=(k-x1)/(x2-x1)
                if 0<t<1: cuts.append(t)
        if y2 != y1:
            for k in range(floor(min(y1,y2))+1,ceil(max(y1,y2))):
                t=(k-y1)/(y2-y1)
                if 0<t<1: cuts.append(t)
        cuts=sorted(set(cuts))
        cells=set()
        def add_cells(x, y):
            cols = [floor(x)]
            rows = [floor(y)]
            if abs(x-round(x))<1e-10: cols=[round(x)-1,round(x)]
            if abs(y-round(y))<1e-10: rows=[round(y)-1,round(y)]
            for row in rows:
                for col in cols: cells.add((row,col))
        for u,v in zip(cuts,cuts[1:]):
            t=(u+v)/2
            add_cells(x1+t*(x2-x1),y1+t*(y2-y1))
        for t in cuts:
            x,y=x1+t*(x2-x1),y1+t*(y2-y1)
            add_cells(x,y)
        if any(not (0<=r<self.height and 0<=c<self.width) for r,c in cells):
            raise ValueError(f"航段经过DEM范围外: {a.id}->{b.id}")
        if any(self.a[r,c]<=self.nodata or not np.isfinite(self.a[r,c]) for r,c in cells):
            raise ValueError(f"航段经过无效DEM像元: {a.id}->{b.id}")
        vals=[float(self.a[r,c]) for r,c in cells]
        return max(vals)


def horizontal_distance_m(a: Node, b: Node):
    # 在两点平均纬度进行WGS84局部度量；与DEM穿格采用同一经纬度直线。
    lat=(a.lat+b.lat)*pi/360
    semi_major=6378137.0
    eccentricity_sq=0.0066943799901413165
    denom=sqrt(1-eccentricity_sq*(1-cos(lat)**2))
    east_radius=semi_major/denom
    north_radius=semi_major*(1-eccentricity_sq)/denom**3
    dx=(b.lon-a.lon)*pi/180*east_radius*cos(lat)
    dy=(b.lat-a.lat)*pi/180*north_radius
    return sqrt(dx*dx+dy*dy)


def make_leg(terrain: Terrain, a: Node, b: Node):
    altitude=terrain.line_max(a,b)+50.0
    h0=a.ground_m+(30.0 if a.id.startswith("S") else 0.0)
    h1=b.ground_m+(30.0 if b.id.startswith("S") else 0.0)
    if altitude < max(h0,h1):
        raise ValueError(f"巡航海拔低于作业高度: {a.id}->{b.id}")
    return Leg(a.id,b.id,horizontal_distance_m(a,b),altitude,altitude-h0,altitude-h1)


def equivalent_range(m: Model, q: float):
    if q < -1e-9 or q > m.max_kg+1e-9: raise ValueError("载荷越界")
    return m.range_empty_m-(m.range_empty_m-m.range_full_m)*(max(0,q)/m.max_kg)**1.5


def leg_energy(m: Model, leg: Leg, q: float):
    """显式假设：标准航程折算水平电耗；重力势能/效率折算爬升附加电耗。"""
    horizontal=m.energy_kwh*leg.distance_m/equivalent_range(m,q)
    climbing=(m.empty_kg+q)*G*leg.climb_m/(3_600_000*m.climb_eta)
    return horizontal+climbing


def leg_time(m: Model, leg: Leg):
    return leg.climb_m/m.climb_mps+leg.distance_m/m.cruise_mps+leg.descent_m/m.descent_mps


def roundtrip(m: Model, outgoing: Leg, returning: Leg, q: float, nboxes: int):
    energy=leg_energy(m,outgoing,q)+leg_energy(m,returning,0.0)
    time=m.prep_s+nboxes*m.load_box_s+leg_time(m,outgoing)+m.handoff_base_s+nboxes*m.handoff_box_s+leg_time(m,returning)
    return energy,time,1-energy/m.energy_kwh


def max_safe_payload(m: Model, out: Leg, back: Leg, reserve: float):
    limit=(1-reserve)*m.energy_kwh
    if roundtrip(m,out,back,0.0,1)[0]>limit+1e-10: return None
    if roundtrip(m,out,back,m.max_kg,1)[0]<=limit+1e-10: return m.max_kg
    lo,hi=0.0,m.max_kg
    for _ in range(50):
        mid=(lo+hi)/2
        if roundtrip(m,out,back,mid,1)[0]<=limit: lo=mid
        else: hi=mid
    return lo
