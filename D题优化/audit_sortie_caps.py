# AI-assisted code: OpenAI Codex; metadata to be verified by team.
from audit_optimize import *
def main():
    e=Engine();rng=random.Random(24928)
    d=json.loads((OUT/'q2_results.json').read_text(encoding='utf8'))['selected']
    ts=[Task(tuple((s['zone'],tuple(s['boxes'])) for s in r['stops'])) for r in d['missions']]
    current=e.evaluate(ts,[r['model'] for r in d['missions']]);results=[]
    for cap in (25,24):
        candidates=[]
        for i in range(len(current['tasks'])):
            for j in range(i+1,len(current['tasks'])):
                ts=list(current['tasks']);ass=list(current['assign']);t=e.task(ts[i].boxes+ts[j].boxes)
                if len(t.stops)>2 or not e.options(t):continue
                ts[i]=t;ass[i]=None;ts.pop(j);ass.pop(j)
                for mode in (0,1,2):
                    c=e.evaluate(ts,ass if mode==0 else None,rule=mode)
                    if c:candidates.append(c)
        if not candidates:
            results.append({'cap':cap,'feasible_found':False});break
        best=min(candidates,key=e.key);current=best
        def score(c):return c['metrics']['total_lateness_s']*30+c['metrics']['makespan_s']
        for it in range(18000):
            ts=list(current['tasks']);ass=list(current['assign']);op=rng.randrange(5)
            if op==0:i=rng.randrange(len(ts));ass[i]=rng.choice(e.options(ts[i]))
            elif op in (1,2):
                i,j=rng.sample(range(len(ts)),2)
                if op==1:ts[i],ts[j]=ts[j],ts[i];ass[i],ass[j]=ass[j],ass[i]
                else:ts.insert(j,ts.pop(i));ass.insert(j,ass.pop(i))
            else:
                i,j=rng.sample(range(len(ts)),2);a=list(ts[i].boxes);b=list(ts[j].boxes)
                x=rng.choice(a);a.remove(x)
                if op==4:y=rng.choice(b);b.remove(y);a.append(y)
                if not a:continue
                b.append(x);ts[i]=e.task(a);ts[j]=e.task(b);ass[i]=ass[j]=None
            if any(len(t.stops)>2 or not e.options(t) for t in ts):continue
            c=e.evaluate(ts,ass)
            if not c:continue
            if e.key(c)<e.key(best):
                best=c
                write(ROOT/'checkpoints'/f'q2_cap_{cap}_latest.json',{k:v for k,v in best.items() if k not in ('tasks','assign')})
            temp=max(.1,80*(1-it/18000))
            if score(c)<=score(current) or rng.random()<math.exp(min(0,(score(current)-score(c))/temp)):current=c
        current=best;record={k:v for k,v in best.items() if k not in ('tasks','assign')}
        write(ROOT/'checkpoints'/f'q2_cap_{cap}.json',record);results.append({'cap':cap,'metrics':best['metrics'],'feasible_found':True})
        print('CAP',cap,best['metrics'],flush=True)
    write(OUT/'q2_sortie_caps.json',{'results':results,'evaluated':e.count,'validated':e.valid,'seed':24928,'no_global_optimality_claim':True})
if __name__=='__main__':main()
