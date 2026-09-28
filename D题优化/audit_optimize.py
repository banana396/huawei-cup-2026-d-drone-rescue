# AI-assisted code: OpenAI Codex; actual model/version/date to be verified by team.
"""Independent baseline audit and resource/packing neighbourhood search.

Physical functions are imported unchanged. Every evaluated feasible schedule is
checked by the existing independent checker; improved incumbents are persisted.
"""
import csv, json, math, random, time, hashlib, shutil
from collections import Counter, defaultdict
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from d_common import *
from solve_q2 import Task, mission_profile, hard_deadline
from optimize_q2 import metrics
from check_q2 import inspect

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'结果'
def write(p,d): p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
def csvwrite(name,rows):
    if not rows:return
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

class Engine:
    def __init__(self):
        self.nodes,self.models,self.boxes=load_inputs();self.res=load_resources();self.terrain=Terrain()
        self.terrain.line_max=lru_cache(None)(self.terrain.line_max)
        self.legs={(a,b):make_leg(self.terrain,self.nodes[a],self.nodes[b]) for a in self.nodes for b in self.nodes if a!=b}
        self.profile=lru_cache(None)(lambda t,m:mission_profile(t,self.models[m],self.boxes,self.legs))
        self.count=0;self.valid=0;self.rejected=0
    def task(self,ids,order=None):
        zones=defaultdict(list)
        for i in ids:zones[self.boxes[i].zone].append(i)
        order=order or sorted(zones)
        return Task(tuple((z,tuple(sorted(zones[z]))) for z in order if zones[z]))
    def due(self,t):return min(hard_deadline(self.boxes[i]) for i in t.boxes)
    def options(self,t):return [m for m in self.models if self.profile(t,m)]
    def evaluate(self,tasks,assign=None,rule=0,rng=None):
        self.count+=1
        ca={u:0. for u in self.res.transport_craft};ba={m:[0.]*n for m,(n,_) in self.res.transport_batteries.items()}
        rows=[];chosen=[]
        for idx,t in enumerate(tasks):
            choices=[]
            for mid,m in self.models.items():
                if assign is not None and assign[idx] and assign[idx]!=mid:continue
                p=self.profile(t,mid)
                if not p:continue
                uid=min((u for u,v in self.res.transport_craft.items() if v==mid),key=lambda u:ca[u])
                bi=min(range(len(ba[mid])),key=lambda b:ba[mid][b]);start=max(ca[uid],ba[mid][bi])
                if any(start+dt>hard_deadline(self.boxes[i])+1e-8 for i,dt in p['deliveries'].items()):continue
                late=sum(max(0,start+dt-self.boxes[i].expected_s) for i,dt in p['deliveries'].items())
                end=start+p['duration'];delivery=max(start+dt for dt in p['deliveries'].values())
                if rule==0:key=(late,end,p['energy'])
                elif rule==1:key=(late,delivery,end)
                elif rule==2:key=(late,p['energy'],end)
                else:key=(late,end*(.65+rng.random()*.7),p['energy'])
                choices.append((key,mid,uid,bi,start,p))
            if not choices:self.rejected+=1;return None
            _,mid,uid,bi,start,p=min(choices,key=lambda x:x[0]);m=self.models[mid]
            end=start+p['duration'];soc=1-p['energy']/m.energy_kwh
            recharge=end+charging_time_s(soc,self.res.transport_batteries[mid][1])
            rows.append({'id':f'Q2-{idx+1:03d}','craft':uid,'model':mid,'battery':f'{mid}-BAT-{bi+1:02d}',
                'start_s':start,'route':[z for z,_ in t.stops], 'stops':[{'zone':z,'boxes':list(ids)} for z,ids in t.stops],
                'return_s':end,'energy_kwh':p['energy'],'return_soc':soc,
                'delivery_s':{i:start+dt for i,dt in p['deliveries'].items()},'battery_recharged_s':recharge})
            ca[uid]=end;ba[mid][bi]=recharge;chosen.append(mid)
        mt=metrics(rows,self.boxes)
        delays=[max(0,v-self.boxes[i].expected_s) for r in rows for i,v in r['delivery_s'].items()]
        mt.update(total_lateness_s=sum(delays),max_lateness_s=max(delays),model_sorties=dict(Counter(chosen)))
        errors=inspect(rows,mt,self.nodes,self.models,self.boxes,self.res,self.terrain)
        if errors:raise AssertionError(errors)
        self.valid+=1
        return {'missions':rows,'metrics':mt,'tasks':tasks,'assign':chosen}
    @staticmethod
    def key(c):
        m=c['metrics'];return (round(m['total_lateness_s'],7),m['makespan_s'],m['sorties'],m['energy_kwh'])
    def save(self,c,label):
        d={k:v for k,v in c.items() if k not in ('tasks','assign')};d['label']=label
        d['validation']={'independent_transport_issues':[],'q2_communication':'not applicable per problem statement'}
        write(ROOT/'checkpoints'/f'q2_{label}.json',d);write(ROOT/'checkpoints'/'q2_best.json',d)
        print('CHECKPOINT',label,d['metrics'],flush=True)

def audit(e):
    original=ROOT.parent/'D题求解'/'结果'
    q2=json.loads((original/'q2_results.json').read_text(encoding='utf8'))['selected']
    q3=json.loads((original/'q3_solution.json').read_text(encoding='utf8'))
    reproduced=json.loads((OUT/'q2_results.json').read_text(encoding='utf8'))['selected']
    assert q2['missions']==reproduced['missions']
    rq3=json.loads((OUT/'q3_solution.json').read_text(encoding='utf8'))
    assert q3['transport_missions']==rq3['transport_missions'] and q3['relay_sorties']==rq3['relay_sorties']
    import openpyxl
    import check_template
    mat=check_template.source_matrices();wb=openpyxl.load_workbook(ROOT/'原始备份'/'结果提交模板_已填.xlsx',read_only=True,data_only=True)
    errors=[]
    for name,rows in mat.items():
        got=list(wb[name].iter_rows(min_row=2,max_row=len(rows)+1,max_col=len(rows[0]),values_only=True))
        for i,(a,b) in enumerate(zip(rows,got)):
            for j,(x,y) in enumerate(zip(a,b)):
                if isinstance(x,(float,int)) and isinstance(y,(float,int)):same=abs(x-y)<1e-8
                else:same=x==y or x=='' and y is None
                if not same:errors.append((name,i,j,x,y))
    assert not errors,errors
    wb.close()
    write(ROOT/'baseline_reproduction.json',{'q2_exact_match':True,'q3_exact_match':True,'excel_issues':errors,'rows':sum(map(len,mat.values())),
        'q2':q2['metrics'],'q3_relay_return_s':max(r['return_s'] for r in q3['relay_sorties']),
        'q3_transport_return_s':max(r['return_s'] for r in q3['transport_missions'])})
    timelines(e,q2['missions'],'before')
    fs=[]
    for r in q2['missions']:
        t=Task(tuple((s['zone'],tuple(s['boxes'])) for s in r['stops']))
        for mid,m in e.models.items():
            p=e.profile(t,mid)
            fs.append({'mission':r['id'],'assigned_model':r['model'],'tested_model':mid,'feasible':p is not None,
                'boxes':','.join(t.boxes),'kg':sum(e.boxes[i].kg for i in t.boxes),'m3':sum(e.boxes[i].m3 for i in t.boxes),
                'duration_s':p['duration'] if p else '', 'energy_kwh':p['energy'] if p else '',
                'soc':1-p['energy']/m.energy_kwh if p else ''})
    csvwrite('task_model_feasibility.csv',fs)
    boxrows=[]
    for i,b in e.boxes.items():
        row=asdict(b);row.update(distance_m=e.legs['O01',b.zone].distance_m,climb_m=e.legs['O01',b.zone].climb_m)
        for mid,m in e.models.items():
            p=e.profile(e.task([i]),mid);row[mid+'_feasible']=p is not None
            row[mid+'_energy']=p['energy'] if p else ''
            row[mid+'_safe_kg']=max_safe_payload(m,e.legs['O01',b.zone],e.legs[b.zone,'O01'],m.reserve)
        boxrows.append(row)
    csvwrite('box_feasibility.csv',boxrows)

def timelines(e,rows,suffix):
    horizon=max(r['return_s'] for r in rows);timeline=[];summary=[]
    for uid,mid in e.res.transport_craft.items():
        seq=sorted((r for r in rows if r['craft']==uid),key=lambda r:r['start_s'])
        end=0;busy=flight=wait_b=0
        for k,r in enumerate(seq):
            # Given the final schedule: first time ANY same-model battery is free
            # in this idle interval. Future assigned reservations are not release constraints.
            intervals=defaultdict(list)
            for x in rows:
                if x['model']==mid:
                    intervals[x['battery']].append((x['start_s'],x['battery_recharged_s']))
            available=[]
            for j in range(1,e.res.transport_batteries[mid][0]+1):
                bid=f'{mid}-BAT-{j:02d}';avail=end
                for a,b in sorted(intervals[bid]):
                    if a-1e-7<=avail<b-1e-7:avail=b
                available.append(avail)
            battery_wait=max(0,min(r['start_s'],min(available))-end)
            wait_b+=battery_wait
            n=sum(len(s['boxes']) for s in r['stops']);m=e.models[mid]
            takeoff=r['start_s']+m.prep_s+n*m.load_box_s
            handoff=sum(m.handoff_base_s+len(s['boxes'])*m.handoff_box_s for s in r['stops'])
            flying=r['return_s']-takeoff-handoff
            timeline.append({'craft':uid,'mission':r['id'],'battery':r['battery'],'prepare_start_s':r['start_s'],'takeoff_s':takeoff,
                'zones':','.join(r['route']),'return_s':r['return_s'],'wait_before_s':r['start_s']-end,
                'battery_unavailability_wait_s':battery_wait,'dispatch_idle_s':max(0,r['start_s']-end-battery_wait),
                'next_task_wait_s':seq[k+1]['start_s']-r['return_s'] if k+1<len(seq) else '',
                'flight_s':flying})
            busy+=r['return_s']-r['start_s'];flight+=flying;end=r['return_s']
        summary.append({'craft':uid,'model':mid,'missions':len(seq),'flight_s':flight,'busy_s':busy,'idle_s':horizon-busy,
                        'battery_wait_s':wait_b,'dispatch_or_no_remaining_task_idle_s':horizon-busy-wait_b,'utilization':busy/horizon,'last_return_s':end})
    csvwrite(f'craft_timeline_{suffix}.csv',timeline);csvwrite(f'craft_utilization_{suffix}.csv',summary)

def main():
    e=Engine();audit(e);rng=random.Random(20260928)
    src=json.loads((OUT/'q2_results.json').read_text(encoding='utf8'))
    tasks=[Task(tuple((s['zone'],tuple(s['boxes'])) for s in r['stops'])) for r in src['selected']['missions']]
    best=None;stage=[]
    def consider(c,label):
        nonlocal best
        if c and (best is None or e.key(c)<e.key(best)):
            best=c;e.save(c,label)
    for rule in range(4):
        c=e.evaluate(tasks,rule=rule,rng=rng);consider(c,f'seed{rule}')
    current=best
    # Fixed packing: change all task orders and aircraft models, not only soft order.
    for it in range(14000):
        ts=list(current['tasks']);ass=list(current['assign']);op=rng.randrange(3)
        if op==0:
            i=rng.randrange(len(ts));ass[i]=rng.choice(e.options(ts[i]))
        elif op==1:
            i,j=rng.sample(range(len(ts)),2);ts[i],ts[j]=ts[j],ts[i];ass[i],ass[j]=ass[j],ass[i]
        else:
            i,j=rng.sample(range(len(ts)),2);ts.insert(j,ts.pop(i));ass.insert(j,ass.pop(i))
        c=e.evaluate(ts,ass)
        if not c:continue
        consider(c,f'fixed_{it}')
        def cost(x):return x['metrics']['total_lateness_s']*20+x['metrics']['makespan_s']+x['metrics']['energy_kwh']*.001
        temp=max(1,120*(1-(it%3500)/3500))
        if cost(c)<=cost(current) or rng.random()<math.exp(min(0,(cost(current)-cost(c))/temp)):current=c
        if it%3500==3499:current=best
    stage.append({'phase':'fixed_packing','metrics':best['metrics']});e.save(best,'fixed_final')
    # Packing neighbourhood: relocate boxes, swap boxes, merge, split, route swap.
    current=best
    for it in range(60000):
        ts=list(current['tasks']);ass=list(current['assign']);op=rng.randrange(9)
        if op<2:
            i=rng.randrange(len(ts));ass[i]=rng.choice(e.options(ts[i]))
        elif op==2:
            i,j=rng.sample(range(len(ts)),2);ts[i],ts[j]=ts[j],ts[i];ass[i],ass[j]=ass[j],ass[i]
        elif op==3:
            i,j=rng.sample(range(len(ts)),2);ts.insert(j,ts.pop(i));ass.insert(j,ass.pop(i))
        elif op in (4,5):
            i,j=rng.sample(range(len(ts)),2);a=list(ts[i].boxes);b=list(ts[j].boxes)
            x=rng.choice(a);a.remove(x)
            if op==5:
                y=rng.choice(b);b.remove(y);a.append(y)
            b.append(x)
            if not a:continue
            ts[i]=e.task(a);ts[j]=e.task(b);ass[i]=ass[j]=None
        elif op==6:
            i,j=sorted(rng.sample(range(len(ts)),2));merged=e.task(ts[i].boxes+ts[j].boxes)
            if len(merged.stops)>3:continue
            ts[i]=merged;ass[i]=None;ts.pop(j);ass.pop(j)
        elif op==7:
            if len(ts)>32:continue
            i=rng.randrange(len(ts));a=list(ts[i].boxes)
            if len(a)<2:continue
            rng.shuffle(a);k=rng.randrange(1,len(a));ts[i]=e.task(a[:k]);ass[i]=None
            ts.insert(i+1,e.task(a[k:]));ass.insert(i+1,None)
        else:
            i=rng.randrange(len(ts));st=list(ts[i].stops)
            if len(st)<2:continue
            rng.shuffle(st);ts[i]=Task(tuple(st));ass[i]=None
        if any(len(t.stops)>3 or not e.options(t) for t in ts):continue
        c=e.evaluate(ts,ass)
        if not c:continue
        consider(c,f'packing_{it}')
        temp=max(.2,80*(1-(it%6000)/6000))
        if cost(c)<=cost(current) or rng.random()<math.exp(min(0,(cost(current)-cost(c))/temp)):current=c
        if it%6000==5999:current=best;print('SEARCH',it,e.count,e.valid,flush=True)
    e.save(best,'final');timelines(e,best['missions'],'after')
    src['selected']={k:v for k,v in best.items() if k not in ('tasks','assign')}
    src['optimization']={'objective_priority':['total_lateness_s','makespan_s','sorties','energy_kwh'],
        'evaluated':e.count,'validated':e.valid,'infeasible':e.rejected,'stages':stage,'seed':20260928,
        'scope':'finite stochastic neighbourhood search; no global optimum claim'}
    write(OUT/'q2_results.json',src)
if __name__=='__main__':main()
