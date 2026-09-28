"""Independent audit supplements; modifies only audit evidence, never inputs."""
import independent_audit as m
from collections import Counter
from copy import deepcopy
import json
from decimal import Decimal, getcontext, ROUND_FLOOR
from types import SimpleNamespace

getcontext().prec=70
def dsin(x):
    term=total=x;n=1
    while True:
        term*=-x*x/Decimal((2*n)*(2*n+1));new=total+term
        if new==total:return total
        total=new;n+=1
def dcos(x):
    term=total=Decimal(1);n=1
    while True:
        term*=-x*x/Decimal((2*n-1)*(2*n));new=total+term
        if new==total:return total
        total=new;n+=1
mp=SimpleNamespace(mpf=Decimal,pi=Decimal('3.141592653589793238462643383279502884197169399375105820974944592307816406'),sin=dsin,cos=dcos,sqrt=lambda x:x.sqrt(),log10=lambda x:x.log10(),floor=lambda x:x.to_integral_value(rounding=ROUND_FLOOR),inf=Decimal('Infinity'))

def q1(a):
    seen=Counter();out=[];before=len(m.issues)
    for mid,z,model,boxtext,kg,volume,reported_t,reported_e,reported_soc in a.rows('Q1_单点组批'):
        ids=boxtext.split(',');seen.update(ids);spec=a.models[model]
        mass=sum(a.boxes[i]['kg'] for i in ids);vol=sum(a.boxes[i]['volume'] for i in ids)
        m.require(all(a.boxes[i]['zone']==z for i in ids),'Q1 zone',mid)
        m.near(mass,kg,'Q1 mass',mid);m.near(vol,volume,'Q1 volume',mid)
        m.require(mass<=spec['kg'] and vol<=spec['volume']+1e-12,'Q1 capacity',mid)
        E=0.;T=spec['prep']+len(ids)*spec['load']+spec['handoff']+len(ids)*spec['perbox']
        for src,dst,q in [('O01',z,mass),(z,'O01',0)]:
            d,H,up,down=a.leg(src,dst)
            L=spec['range0']-(spec['range0']-spec['rangef'])*(q/spec['kg'])**1.5
            E+=spec['energy']*d/L+(spec['empty']+q)*9.80665*up/(3600000*spec['eta'])
            T+=up/spec['climb']+d/spec['speed']+down/spec['descend']
        soc=1-E/spec['energy'];m.require(soc>=spec['reserve_percent']/100,'Q1 SOC',mid)
        m.near(T,reported_t,'Q1 time',mid,tol=1e-6);m.near(E,reported_e,'Q1 energy',mid,tol=1e-8)
        m.near(soc*100,reported_soc,'Q1 SOC column',mid,tol=1e-6)
        out.append({'mission':mid,'model':model,'energy_kwh':E,'duration_s':T,'return_soc':soc})
    m.require(seen==Counter({i:1 for i in a.boxes}),'Q1 coverage')
    result={'sorties':len(out),'coverage':len(seen),'energy_kwh':sum(r['energy_kwh'] for r in out),'cumulative_time_s':sum(r['duration_s'] for r in out),'minimum_soc':min(r['return_soc'] for r in out),'issues':m.issues[before:],'rows':out,'scope':'Workbook batches only; no optimization or safe-payload sensitivity re-solving.'}
    m.save('independent_q1_check.json',result);return result

def negative_tests():
    a=m.Audit();base=a.transport_from_excel();results=[]
    def trial(name,edit,expected):
        m.issues.clear();rows=deepcopy(base);edit(rows);a.audit_transport(rows,'NEGATIVE_TEST')
        kinds={r['kind'] for r in m.issues};passed=expected in kinds
        results.append({'test':name,'detected':passed,'expected_error':expected,'observed_error_kinds':sorted(kinds)})
        assert passed,(name,kinds)
    trial('stored energy +0.1 kWh',lambda r:r[0].update(energy_kwh=r[0]['energy_kwh']+.1),'energy mismatch')
    trial('stored return +1 s',lambda r:r[0].update(return_s=r[0]['return_s']+1),'return mismatch')
    trial('stored delivery +1 s',lambda r:r[0]['delivery_s'].update({next(iter(r[0]['delivery_s'])):next(iter(r[0]['delivery_s'].values()))+1}),'delivery mismatch')
    trial('duplicate a cargo box',lambda r:r[0]['stops'][0]['boxes'].append(r[0]['stops'][0]['boxes'][0]),'box coverage')
    trial('unavailable battery identifier',lambda r:r[0].update(battery='A-BAT-99'),'unknown battery')
    trial('aircraft overlaps another sortie',lambda r:r[3].update(start_s=0),'resource overlap')
    m.issues.clear();r=a.relay
    assert m.charge(0,100)==100 and abs(m.charge(.9,100)-35)<1e-12 and m.charge(1,100)==0
    results.append({'test':'two-stage charge endpoints 0%,90%,100%','detected':True})
    m.save('negative_tests.json',results);return results

def high_precision(a):
    """Resolve chosen table-state discrepancies with 70-digit static slab geometry.

    Uses exact binary input values, a separately implemented arbitrary-precision
    intersection and loss calculation. No reuse of old line-of-sight results.
    Phase endpoint times are also recomputed from raw nodes, DEM and speeds at
    70 digits; only submitted start times retain their exact binary input value.
    """
    D=mp.mpf
    a.audit_transport(a.assignment['transport_missions'],'Q3');a.audit_relays()
    def hp_distance(p,g):
        lat=(p[1]+g[1])*mp.pi/360;e=D(.0066943799901413165)
        N=6378137/mp.sqrt(1-e*mp.sin(lat)**2);M=6378137*(1-e)/(1-e*mp.sin(lat)**2)**D(1.5)
        return mp.sqrt(((p[0]-g[0])*mp.pi/180*N*mp.cos(lat))**2+((p[1]-g[1])*mp.pi/180*M)**2)
    hp_phases=[]
    for task in a.assignment['transport_missions']:
        spec=a.models[task['model']];now=D(task['start_s'])+D(spec['prep'])+sum(len(s['boxes']) for s in task['stops'])*D(spec['load']);prev='O01'
        for stop in task['stops']+[{'zone':'O01','boxes':[]}]:
            dst=stop['zone'];p=list(map(D,a.nodes[prev]));q=list(map(D,a.nodes[dst]));H=D(a.dem.maxground(a.nodes[prev],a.nodes[dst]))+50
            h0=p[2]+(30 if prev!='O01' else 0);h1=q[2]+(30 if dst!='O01' else 0)
            positions=[(*p[:2],h0),(*p[:2],H),(*q[:2],H),(*q[:2],h1)]
            durations=[(H-h0)/D(spec['climb']),hp_distance(p,q)/D(spec['speed']),(H-h1)/D(spec['descend'])]
            for i,kind in enumerate(('爬升','巡航','下降')):
                hp_phases.append({'mission':task['id'],'phase':kind,'t0':now,'t1':now+durations[i],'a':positions[i],'b':positions[i+1]});now+=durations[i]
            if dst!='O01':now+=D(spec['handoff'])+len(stop['boxes'])*D(spec['perbox'])
            prev=dst
    data=json.loads((m.OUT/'table_boundary_point_discrepancies.json').read_text(encoding='utf8'))
    # Prefer a terrain-clearance jump with substantial positive clearance and margin.
    cases=[r for r in data if r['direct_clearance_m']>.01 and r['direct_margin_db']>1]
    cases+=sorted([r for r in data if r['recorded_mode']=='直连'],key=lambda r:r['direct_margin_db'])[:3]
    out=[]
    for rec in cases[:12]:
        phase=next(p for p in hp_phases if p['mission']==rec['mission'] and p['phase']==rec['phase'] and p['t0']<=D(rec['probe_time_s'])<=p['t1'])
        t=D(rec['probe_time_s']);s=(t-D(phase['t0']))/(D(phase['t1'])-D(phase['t0']))
        p=[D(x)+(D(y)-D(x))*s for x,y in zip(phase['a'],phase['b'])];g=list(map(D,a.gate));dem=a.dem
        def pixel(pt):return ((pt[0]-D(dem.origin[0]))/D(dem.dx)+D(dem.shift),(D(dem.origin[1])-pt[1])/D(dem.dy)+D(dem.shift))
        x,y=pixel(g);X,Y=pixel(p);minimum=mp.inf;witness=None
        for row in range(int(mp.floor(min(y,Y)))-1,int(mp.floor(max(y,Y)))+1):
            for col in range(int(mp.floor(min(x,X)))-1,int(mp.floor(max(x,X)))+1):
                u=D(0);v=D(1)
                for origin,delta,low in ((x,X-x,col),(y,Y-y,row)):
                    if delta==0:
                        if not low<=origin<=low+1:u=D(2)
                    else:
                        l,h=sorted(((D(low)-origin)/delta,(D(low+1)-origin)/delta));u=max(u,l);v=min(v,h)
                if u>v:continue
                clear=g[2]+(p[2]-g[2])*(u if p[2]>=g[2] else v)-D(float(dem.z[row,col]))
                if clear<minimum:minimum=clear;witness=(row,col)
        dist=mp.sqrt(hp_distance(p,g)**2+(p[2]-g[2])**2)
        margin=D(a.limit('运输无人机','固定网关 G01'))-D(32.45)-20*mp.log10(D(a.radio['传播参数','f']))-20*mp.log10(dist/1000)-(D(a.radio['传播参数','Lobs']) if minimum<0 else 0)
        actual='直连' if margin>=0 else '需中继'
        excelrows=[(i,list(row)) for i,row in enumerate(a.book['Q3_通信保障'].iter_rows(min_row=2,values_only=True),2) if row[0]==rec['mission'] and row[1]==rec['phase'] and row[2]<=float(t)<=row[3]]
        out.append({**rec,'high_precision_margin_db':str(margin),'high_precision_clearance_m':str(minimum),'witness_pixel':witness,'actual_mode_high_precision':actual,'mismatch_confirmed':(rec['recorded_mode']=='直连')!=(margin>=0),'excel_rows':excelrows})
    m.save('high_precision_table_counterexamples.json',out);return out

if __name__=='__main__':
    a=m.Audit();first=q1(a);errors=list(m.issues);tests=negative_tests();extra=high_precision(a)
    print(json.dumps({'Q1':{k:v for k,v in first.items() if k!='rows'},'negative_tests':tests,'high_precision_cases':len(extra),'confirmed':sum(r['mismatch_confirmed'] for r in extra),'issues':errors+m.issues},ensure_ascii=False,indent=2))
