# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""中继往返与悬停资源计算。"""
from __future__ import annotations

from d_common import G,Node,horizontal_distance_m
from radio import Position


def relay_route(hover:Position,nodes,terrain,relay):
    o=nodes['O01']
    h_o=o.ground_m
    d=horizontal_distance_m(o,Node('hover',hover.lon,hover.lat,hover.alt_m))
    temp=Node('hover',hover.lon,hover.lat,hover.alt_m)
    cruise=max(terrain.line_max(o,temp)+50,hover.alt_m)
    climb_out=cruise-h_o
    descent_out=cruise-hover.alt_m
    climb_back=cruise-hover.alt_m
    descent_back=cruise-h_o
    outward=climb_out/relay.climb_mps+d/relay.cruise_mps+descent_out/relay.descent_mps
    returning=climb_back/relay.climb_mps+d/relay.cruise_mps+descent_back/relay.descent_mps
    energy=(relay.cruise_kw*(2*d/relay.cruise_mps)/3600+
            relay.takeoff_kg*G*(climb_out+climb_back)/(3_600_000*relay.climb_eta))
    return {'out_s':outward,'back_s':returning,'flight_energy_kwh':energy,
            'cruise_alt_m':cruise,'distance_m':d,
            'max_service_s':((1-relay.reserve)*relay.energy_kwh-energy)/(relay.hover_kw+relay.comm_kw)*3600}
