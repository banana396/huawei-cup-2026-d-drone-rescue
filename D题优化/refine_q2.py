# AI-assisted code: OpenAI Codex; metadata to be verified by team.
from audit_optimize import *

def main():
    e=Engine();rng=random.Random(92871)
    old=json.loads((ROOT/'checkpoints'/'q2_best.json').read_text(encoding='utf8'))
    ts=[Task(tuple((s['zone'],tuple(s['boxes'])) for s in r['stops'])) for r in old['missions']]
    best=e.evaluate(ts,[r['model'] for r in old['missions']]);best_small=None
    def consider(c,label):
        nonlocal best,best_small
        if c and (e.key(c)<e.key(best)):
            best=c;e.save(c,label)
        if c and len(c['missions'])<=26 and (best_small is None or e.key(c)<e.key(best_small)):
            best_small=c;write(ROOT/'checkpoints'/'q2_at_most_26.json',{k:v for k,v in c.items() if k not in ('tasks','assign')})
    def cost(c):return c['metrics']['total_lateness_s']*30+c['metrics']['makespan_s']+len(c['missions'])*3+c['metrics']['energy_kwh']*.05
    seeds=[]
    for attempt in range(700):
        tasks=[];ass=[]
        for zone in sorted({b.zone for b in e.boxes.values()}):
            ids=[i for i,b in e.boxes.items() if b.zone==zone]
            ids.sort(key=lambda i:(hard_deadline(e.boxes[i]),-e.boxes[i].kg))
            while ids:
                mid=rng.choices(['A','B','C'],[4,2,1.4])[0];batch=[ids.pop(0)]
                for i in list(ids):
                    t=e.task(batch+[i])
                    if e.profile(t,mid):batch.append(i);ids.remove(i)
                t=e.task(batch);opts=e.options(t)
                if not opts:raise ValueError(t)
                tasks.append(t);ass.append(mid if mid in opts else opts[0])
        pairs=sorted(zip(tasks,ass),key=lambda x:(e.due(x[0]),min(e.boxes[i].expected_s for i in x[0].boxes)))
        c=e.evaluate([t for t,m in pairs],rule=attempt%4,rng=rng)
        if c:seeds.append(c);consider(c,f'binseed_{attempt}')
    seeds=sorted(seeds,key=cost)[:8]+[best]
    for restart,current in enumerate(seeds):
        for it in range(22000):
            ts=list(current['tasks']);ass=list(current['assign']);op=rng.randrange(9)
            if op<2:
                i=rng.randrange(len(ts));ass[i]=rng.choice(e.options(ts[i]))
            elif op in (2,3):
                i,j=rng.sample(range(len(ts)),2)
                if op==2:ts[i],ts[j]=ts[j],ts[i];ass[i],ass[j]=ass[j],ass[i]
                else:ts.insert(j,ts.pop(i));ass.insert(j,ass.pop(i))
            elif op in (4,5,6):
                i,j=rng.sample(range(len(ts)),2)
                if rng.random()<.85:
                    js=[j for j in range(len(ts)) if j!=i and set(ts[i].boxes)!=set(ts[j].boxes) and set(z for z,_ in ts[i].stops)&set(z for z,_ in ts[j].stops)]
                    if not js:continue
                    j=rng.choice(js)
                a=list(ts[i].boxes);b=list(ts[j].boxes)
                if op==6:
                    ts[i]=e.task(a+b);ass[i]=None;ts.pop(j);ass.pop(j)
                else:
                    x=rng.choice(a);a.remove(x)
                    if op==5:y=rng.choice(b);b.remove(y);a.append(y)
                    b.append(x)
                    ts[j]=e.task(b);ass[j]=None
                    if a:ts[i]=e.task(a);ass[i]=None
                    else:ts.pop(i);ass.pop(i)
            elif op==7:
                if len(ts)>=28:continue
                i=rng.randrange(len(ts));a=list(ts[i].boxes)
                if len(a)<2:continue
                rng.shuffle(a);k=rng.randrange(1,len(a));ts[i]=e.task(a[:k]);ass[i]=None
                ts.insert(i+1,e.task(a[k:]));ass.insert(i+1,None)
            else:
                i=rng.randrange(len(ts));st=list(ts[i].stops)
                if len(st)<2:continue
                rng.shuffle(st);ts[i]=Task(tuple(st));ass[i]=None
            if any(len(t.stops)>2 or not e.options(t) for t in ts):continue
            # Keep Q4 structurally feasible (at least three nonempty components).
            parent={b.zone:b.zone for b in e.boxes.values()}
            def find(z):
                while parent[z]!=z:z=parent[z]
                return z
            for t in ts:
                for z,_ in t.stops[1:]:parent[find(z)]=find(t.stops[0][0])
            if len({find(z) for z in parent})<3:continue
            c=e.evaluate(ts,ass)
            if not c:continue
            consider(c,f'refine_{restart}_{it}')
            temp=max(.1,80*(1-(it%5500)/5500))
            if cost(c)<=cost(current) or rng.random()<math.exp(min(0,(cost(current)-cost(c))/temp)):current=c
        print('RESTART',restart,'best',best['metrics'],'evaluated',e.count,flush=True)
    e.save(best,'refined_final');timelines(e,best['missions'],'after')
    source=json.loads((OUT/'q2_results.json').read_text(encoding='utf8'))
    source['selected']={k:v for k,v in best.items() if k not in ('tasks','assign')}
    source['optimization']['refinement']={'evaluated':e.count,'validated':e.valid,'seed':92871,'restarts':len(seeds)}
    write(OUT/'q2_results.json',source)
if __name__=='__main__':main()
