# AI-assisted code: OpenAI Codex; metadata to be verified by team.
"""Search DEM-derived relay sites; aggregate coverage across transport missions.

No benchmark coordinate is used. Coarse coverage is only a search filter;
independent exact and continuous-interval checks gate the final result.
"""
import json, math, itertools, copy, random, sys, time
from collections import defaultdict
from pathlib import Path
import numpy as np
from audit_optimize import Engine,write,ROOT,OUT,csvwrite
from diagnose_q3 import transport_phases
from radio import Position,direct,gateway,link_budget
from relay_flight import relay_route
from d_common import charging_time_s

def main():
    e=Engine();radio=e.res.radio;rm=e.res.relay_models['R'];gate=gateway(e.nodes,radio)
    q2=json.loads((OUT/'q2_results.json').read_text(encoding='utf8'))['selected']
    missions=q2['missions'];samples=[];ranges=[]
    for r in missions:
        lo=len(samples)
        for phase in transport_phases(r,e.nodes,e.models,e.legs):
            n=max(1,math.ceil((phase.t1-phase.t0)/30))
            for k in range(n+1):
                t=phase.t0+(phase.t1-phase.t0)*k/n;p=phase.at(t)
                if direct(p,e.nodes,e.terrain,radio,'exact')['margin_db']<.05:
                    samples.append((r['id'],t-r['start_s'],p))
        ranges.append((lo,len(samples)))
    coords=[(n.lon,n.lat) for n in e.nodes.values()]
    lo=np.min(coords,axis=0);hi=np.max(coords,axis=0)
    raw=[(x,y,h) for x in np.linspace(lo[0],hi[0],23) for y in np.linspace(lo[1],hi[1],23) for h in (300,)]
    o=e.nodes['O01']
    raw.extend((n.lon,n.lat,h) for n in e.nodes.values() for h in (150,225,300))
    raw.extend(((o.lon+n.lon)/2,(o.lat+n.lat)/2,h) for n in e.nodes.values() for h in (150,225,300))
    sites=[];masks=[];routes=[];full=(1<<len(samples))-1
    for idx,(lon,lat,h) in enumerate(raw):
        try:p=Position(float(lon),float(lat),e.terrain.sample(lon,lat)+h)
        except ValueError:continue
        back=link_budget(p,gate,e.terrain,radio,'中继回传端','固定网关 G01','exact')
        if back['margin_db']<.2:continue
        route=relay_route(p,e.nodes,e.terrain,rm)
        if route['max_service_s']<1500:continue
        mask=0
        for j,(_,t,point) in enumerate(samples):
            if link_budget(point,p,e.terrain,radio,'运输无人机','中继接入端','exact')['margin_db']>=.2:mask|=1<<j
        sites.append(p);masks.append(mask);routes.append(route)
        if idx%100==0:print('SITES',idx,'usable',len(sites),'blind',len(samples),flush=True)
    target_masks=[((1<<b)-(1<<a)) for a,b in ranges]
    pairs=[]
    for i in range(len(sites)):
        for j in range(i+1,len(sites)):
            union=masks[i]|masks[j];covered=[k for k,m in enumerate(target_masks) if m&union==m]
            pairs.append((len(covered),(union&full).bit_count(),-(routes[i]['flight_energy_kwh']+routes[j]['flight_energy_kwh']),i,j,covered))
    pairs.sort(reverse=True)
    evidence={'source_q2':q2,'sampling_s':30,'sites':[{'position':[p.lon,p.lat,p.alt_m],'route':r,'mask':str(m)} for p,r,m in zip(sites,routes,masks)],
              'samples':[[mid,t,[p.lon,p.lat,p.alt_m]] for mid,t,p in samples],'ranges':ranges,
              'top_pairs':[{'site_indices':list(x[3:5]),'covered_mission_indices':x[5],'sample_coverage':x[1]} for x in pairs[:50]]}
    write(OUT/'q3_spatial_search.json',evidence)
    print('TOP',[(x[0],x[1],x[3:5],x[5]) for x in pairs[:4]],flush=True)

if __name__=='__main__':main()
