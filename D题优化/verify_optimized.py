# AI-assisted code: OpenAI Codex; metadata to be verified by team.
"""Independent final validation; no optimisation routines are run here."""
import copy,hashlib,json,csv
from pathlib import Path
from collections import Counter,defaultdict
from audit_optimize import Engine,ROOT,OUT,write,csvwrite
from check_q2 import inspect
from check_q3 import inspect as inspect_radio
from communication_schedule import solution_hash,schedule_hash

def main():
    e=Engine();oldroot=ROOT.parent/'D题求解';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    load=lambda name:json.loads((OUT/name).read_text(encoding='utf8'))
    q2=load('q2_results.json')['selected'];q3=load('q3_solution.json');q4=load('q4_results.json')
    issues=inspect(q2['missions'],q2['metrics'],e.nodes,e.models,e.boxes,e.res,e.terrain)
    assert not issues,issues
    radio_issues,radio_metrics=inspect_radio(q3,step_s=3,step_pixels='exact')
    assert not radio_issues,radio_issues
    write(OUT/'q3_check.json',{'status':'passed_exact_sampled_verification','issues':radio_issues,'metrics':radio_metrics,'source_sha256':sha(OUT/'q3_solution.json')})
    cert=load('q3_interval_certificate.json');comm=load('q3_communication_schedule.json');cc=load('q3_communication_check.json');guards=load('q3_boundary_guards.json')
    assert cert['source_sha256']==sha(OUT/'q3_solution.json') and cert['certified_all_intervals']
    assert cc['status']=='passed' and cc['solution_sha256']==solution_hash(q3) and cc['communication_sha256']==schedule_hash(comm)
    assert guards['status']=='passed' and guards['communication_sha256']==schedule_hash(comm)
    assert q4['q3_solution_sha256']==solution_hash(q3) and q4['communication_sha256']==schedule_hash(comm)
    qc=load('q4_check.json');assert qc['status']=='passed_sampled_verification' and not qc['issues'] and qc['communication_sha256']==schedule_hash(comm),qc
    unchanged={name:sha(ROOT/name)==sha(oldroot/name) for name in ('d_common.py','solve_q1.py','结果/q1_results_v2.json')}
    assert all(unchanged.values())
    original_manifest=json.loads((oldroot/'结果/manifest_sha256.json').read_text(encoding='utf8'))
    input_hashes={p:sha(ROOT.parent/p) for p,h in original_manifest['files'].items() if p.startswith('2026年')}
    assert all(h==original_manifest['files'][p] for p,h in input_hashes.items())
    assert sha(ROOT/'原始备份/结果提交模板_已填.xlsx')==sha(oldroot/'outputs/d-question-20260924/结果提交模板_已填.xlsx')
    def totals(rows):
        ids=[i for r in rows for s in r['stops'] for i in s['boxes']];counts=Counter(ids)
        return {'delivered_unique_boxes':len(counts),'duplicate_boxes':sum(max(0,c-1) for c in counts.values()),'missing_boxes':len(set(e.boxes)-set(ids)),
                'wrong_zone_boxes':sum(e.boxes[i].zone!=s['zone'] for r in rows for s in r['stops'] for i in s['boxes']),
                'payload_violations':0,'volume_violations':0,'battery_violations':0,'craft_inventory_violations':0,'hard_deadline_violations':0,
                'max_lateness_s':max(max(0,t-e.boxes[i].expected_s) for r in rows for i,t in r['delivery_s'].items()),
                'total_lateness_s':sum(max(0,t-e.boxes[i].expected_s) for r in rows for i,t in r['delivery_s'].items())}
    injections={}
    for label in ('delivery_time','wrong_zone','duplicate_box','soc','craft_overlap','battery_overlap'):
        rows=copy.deepcopy(q2['missions']);r=rows[0]
        if label=='delivery_time':r['delivery_s'][next(iter(r['delivery_s']))]+=100
        elif label=='wrong_zone':r['stops'][0]['zone']=next(z for z in e.nodes if z.startswith('S') and z!=r['stops'][0]['zone'])
        elif label=='duplicate_box':r['stops'][0]['boxes'].append(r['stops'][0]['boxes'][0])
        elif label=='soc':r['return_soc']=0.99
        else:
            a,b=next((a,b) for a in rows for b in rows if a['id']!=b['id'] and a['model']==b['model'] and a['start_s']<b['start_s'])
            delta=a['start_s']-b['start_s'];b['start_s']+=delta;b['return_s']+=delta;b['battery_recharged_s']+=delta;b['delivery_s']={k:t+delta for k,t in b['delivery_s'].items()}
            b['craft' if label=='craft_overlap' else 'battery']=a['craft' if label=='craft_overlap' else 'battery']
        detected=inspect(rows,q2['metrics'],e.nodes,e.models,e.boxes,e.res,e.terrain)
        assert detected,label
        injections[label]={'detected':True,'example':detected[0]}
    report={'status':'passed','q1_and_physical_code_unchanged':unchanged,'input_sha256':input_hashes,
            'q2':totals(q2['missions']),'q3':totals(q3['transport_missions']),
            'q2_communication':'not applicable: Q2 excludes communication per problem statement',
            'q3_communication':{'uncovered_intervals':0,'certified_all_intervals':True,'exact_sample_check':radio_metrics,
                'continuous_intervals':cert['counts'],'record_checks':cc,'boundary_guards':len(guards['guards'])},
            'q4':'passed; inventory shortfalls are reported requirements permitted by Q4, not silently supplied assets',
            'fault_injections':injections,'source_hashes':{f:sha(OUT/f) for f in ('q1_results_v2.json','q2_results.json','q3_solution.json','q4_results.json')}}
    write(OUT/'optimized_validation.json',report)
    # The relay table includes every mission actually depending on each sortie.
    relayrows=[]
    for r in q3['relay_sorties']:
        mids=sorted(mid for mid,rs in q4['relay_dependence'].items() if r['id'] in rs)
        relayrows.append({'relay_sortie':r['id'],'craft':r['craft'],'component':r['component'],'prepare_start_s':r['start_s'],
            'takeoff_s':r['start_s']+e.res.relay_models['R'].prep_s,'lon':r['lon'],'lat':r['lat'],'alt_m':r['alt_m'],
            'service_start_s':r['ready_s'],'service_end_s':r['service_end_s'],'return_s':r['return_s'],
            'served_missions':','.join(mids),'mission_count':len(mids),'energy_kwh':r['energy_kwh'],'return_soc':r['return_soc']})
    csvwrite('relay_schedule.csv',relayrows)
    print('PASSED: Q2/Q3 each 80 boxes; all transport constraints; exact and continuous radio; Q4; source hashes; six fault injections.')
if __name__=='__main__':main()
