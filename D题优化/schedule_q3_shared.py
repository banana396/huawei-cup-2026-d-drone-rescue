# AI-assisted code: OpenAI Codex; metadata to be verified by team.
from optimize_q3_shared import *
from audit_optimize import Task,inspect,metrics,hard_deadline
from check_q3 import inspect as check_radio

def main():
    e=Engine();res=e.res;rm=res.relay_models['R'];rng=random.Random(3928)
    spatial=json.loads((OUT/'q3_spatial_search.json').read_text(encoding='utf8'))
    source=spatial['source_q2'];old=source['missions'];sites=spatial['sites'];samples=spatial['samples']
    target=[(1<<b)-(1<<a) for a,b in spatial['ranges']];masks=[int(s['mask']) for s in sites]
    tasks=[Task(tuple((s['zone'],tuple(s['boxes'])) for s in r['stops'])) for r in old]
    profiles=[e.profile(t,r['model']) for t,r in zip(tasks,old)]
    bounds=[(min((samples[i][1] for i in range(a,b)),default=0)-35,max((samples[i][1] for i in range(a,b)),default=0)+35) for a,b in spatial['ranges']]
    leads=[rm.prep_s+s['route']['out_s']+rm.link_setup_s for s in sites]
    anchors=set(i for p in spatial['top_pairs'] for i in p['site_indices'])
    if len(anchors)>35:anchors=set(sorted(anchors,key=lambda i:-masks[i].bit_count())[:35])
    full=(1<<len(old))-1;best=None;tested=feasible=0;shortlist=[]
    def schedule(a,j,k,cut,order):
        nonlocal tested,feasible
        tested+=1
        late_ready=cut+sites[j]['route']['back_s']+rm.turnaround_s+leads[k]
        ca={u:0. for u in res.transport_craft};ba={m:[0.]*v[0] for m,v in res.transport_batteries.items()}
        rows=[];which={};windows=[]
        for index,t in enumerate(tasks):
            req=target[index]&~masks[a];first,last=bounds[index]
            opts=[]
            if not target[index]:opts=[(0,math.inf,'direct')]
            elif not req:opts=[(max(0,leads[a]-first),math.inf,'anchor')]
            else:
                if req&masks[j]==req:opts.append((max(0,max(leads[a],leads[j])-first),cut-last,'early'))
                if req&masks[k]==req:opts.append((max(0,max(leads[a],late_ready)-first),math.inf,'late'))
            windows.append(opts)
        if any(not o for o in windows):return None
        for index in order:
            t=tasks[index];mid=old[index]['model'];m=e.models[mid];p=profiles[index]
            uid=min((u for u,v in res.transport_craft.items() if v==mid),key=lambda u:ca[u])
            bi=min(range(len(ba[mid])),key=lambda b:ba[mid][b]);base=max(ca[uid],ba[mid][bi]);choices=[]
            for release,latest,role in windows[index]:
                start=max(base,release)
                if start>latest+1e-8:continue
                if any(start+dt>hard_deadline(e.boxes[i])+1e-8 for i,dt in p['deliveries'].items()):continue
                choices.append((start,role))
            if not choices:return None
            start,role=min(choices);end=start+p['duration'];soc=1-p['energy']/m.energy_kwh
            recharge=end+charging_time_s(soc,res.transport_batteries[mid][1])
            row={'id':f'Q3-{index+1:03d}','craft':uid,'model':mid,'battery':f'{mid}-BAT-{bi+1:02d}',
                 'start_s':start,'route':[z for z,_ in t.stops],'stops':[{'zone':z,'boxes':list(ids)} for z,ids in t.stops],
                 'return_s':end,'energy_kwh':p['energy'],'return_soc':soc,'delivery_s':{i:start+dt for i,dt in p['deliveries'].items()},'battery_recharged_s':recharge}
            rows.append(row);which[index]=role;ca[uid]=end;ba[mid][bi]=recharge
        # Tighten service windows using all potentially needed blind intervals.
        anchor_end=max([leads[a]+.01]+[r['start_s']+bounds[int(r['id'][-3:])-1][1] for r in rows if target[int(r['id'][-3:])-1]])
        early_end=max([leads[j]+.01]+[r['start_s']+bounds[int(r['id'][-3:])-1][1] for r in rows if which[int(r['id'][-3:])-1]=='early'])
        late_end=max([late_ready+.01]+[r['start_s']+bounds[int(r['id'][-3:])-1][1] for r in rows if which[int(r['id'][-3:])-1]=='late'])
        relays=[]
        def launch(site,craft,start,end,component):
            rt=sites[site]['route'];lon,lat,alt=sites[site]['position'];arrival=start+rm.prep_s+rt['out_s'];ready=arrival+rm.link_setup_s
            energy=rt['flight_energy_kwh']+rm.hover_kw*(end-arrival)/3600+rm.comm_kw*(end-ready)/3600
            if energy>(1-rm.reserve)*rm.energy_kwh or end<ready:return False
            back=end+rt['back_s'];soc=1-energy/rm.energy_kwh
            relays.append({'id':f'R-{len(relays)+1:03d}','craft':craft,'component':component,'site':f'SEARCH-{site}',
                'lon':lon,'lat':lat,'alt_m':alt,'agl_m':alt-e.terrain.sample(lon,lat),'start_s':start,'arrival_s':arrival,'ready_s':ready,
                'service_end_s':end,'return_s':back,'component_recharged_s':back+charging_time_s(soc,res.relay_components['R'][1]),
                'energy_kwh':energy,'return_soc':soc,'route':rt})
            return True
        if not launch(a,'R01',0,anchor_end,'R-EC-01'):return None
        if not launch(j,'R02',0,early_end,'R-EC-02'):return None
        # Original searched transition can have idle slack after earlier end.
        late_start=cut+sites[j]['route']['back_s']+rm.turnaround_s
        if not launch(k,'R02',late_start,late_end,'R-EC-03'):return None
        mt=metrics(rows,e.boxes)
        issues=inspect(rows,mt,e.nodes,e.models,e.boxes,res,e.terrain)
        if issues:raise AssertionError(issues)
        delays=[max(0,t-e.boxes[i].expected_s) for r in rows for i,t in r['delivery_s'].items()]
        mt.update(total_lateness_s=sum(delays),max_lateness_s=max(delays),joint_makespan_s=max(mt['makespan_s'],max(r['return_s'] for r in relays)),relay_energy_kwh=sum(r['energy_kwh'] for r in relays))
        feasible+=1
        return {'transport_missions':sorted(rows,key=lambda r:r['id']),'relay_sorties':relays,'metrics':mt,
                'search_parameters':{'anchor':a,'early_site':j,'late_site':k,'cut_s':cut,'order':order},
                'status':'sample_cover_candidate_pending_continuous_validation','q2_inheritance':'same boxes/routes/models; resource assignments and times jointly rescheduled'}
    def key(c):
        m=c['metrics'];return(m['total_lateness_s'],m['joint_makespan_s'],len(c['relay_sorties']),m['relay_energy_kwh'])
    orders=[list(range(len(old))),sorted(range(len(old)),key=lambda i:(e.due(tasks[i]),min(e.boxes[b].expected_s for b in tasks[i].boxes))),
            sorted(range(len(old)),key=lambda i:old[i]['start_s'])]
    for a in sorted(anchors):
        req=[m&~masks[a] for m in target];signatures={}
        for j in range(len(sites)):
            if a==j:continue
            cover=sum(1<<idx for idx,m in enumerate(req) if m&masks[j]==m)
            # Retain lowest lead and energy representative of each coverage signature.
            if cover not in signatures or leads[j]+100*sites[j]['route']['flight_energy_kwh']<leads[signatures[cover]]+100*sites[signatures[cover]]['route']['flight_energy_kwh']:signatures[cover]=j
        mobile=sorted(signatures.items(),key=lambda x:-x[0].bit_count())[:25]
        for (mj,j),(mk,k) in itertools.permutations(mobile,2):
            if mj|mk!=full:continue
            early_only=[i for i in range(len(old)) if mj>>i&1 and not mk>>i&1]
            order=sorted(range(len(old)),key=lambda i:(i not in early_only,e.due(tasks[i]),old[i]['start_s']))
            for cut in range(1800,6501,150):
                for ordering in [order]+orders:
                    c=schedule(a,j,k,cut,ordering)
                    if c and (best is None or key(c)<key(best)):
                        best=c;write(ROOT/'checkpoints'/'q3_shared_search_best.json',c)
                        print('JOINT',tested,c['metrics'],c['search_parameters'],flush=True)
        print('ANCHOR_DONE',a,'tested',tested,'feasible',feasible,flush=True)
    if best is None:raise RuntimeError('No feasible shared-relay schedule found')
    # Local changes to task order and transition time; preserve best checkpoint.
    current=best
    for it in range(10000):
        p=current['search_parameters'];order=list(p['order']);cut=p['cut_s']
        if rng.random()<.25:cut=max(1000,cut+rng.choice([-150,-60,-15,15,60,150]))
        else:
            i,j=rng.sample(range(len(order)),2);order[i],order[j]=order[j],order[i]
        c=schedule(p['anchor'],p['early_site'],p['late_site'],cut,order)
        if not c:continue
        if key(c)<key(best):best=c;write(ROOT/'checkpoints'/'q3_shared_search_best.json',c);print('JOINT_LOCAL',it,c['metrics'],flush=True)
        cost=lambda x:x['metrics']['total_lateness_s']*20+x['metrics']['joint_makespan_s']
        temp=max(.1,80*(1-it/10000))
        if cost(c)<=cost(current) or rng.random()<math.exp(min(0,(cost(current)-cost(c))/temp)):current=c
    errors,mt=check_radio(best,step_s=3,step_pixels='exact')
    write(OUT/'q3_shared_search_check.json',{'issues':errors,'metrics':mt,'tested':tested,'transport_feasible':feasible})
    print('FINAL_SHARED',best['metrics'],'radio_errors',errors,flush=True)
    write(ROOT/'checkpoints'/'q3_shared_search_best.json',best)
    if errors:raise RuntimeError(errors)
    best['status']='passed_exact_sampled_verification; continuous certificate stored separately'
    write(OUT/'q3_solution.json',best)

if __name__=='__main__':main()
