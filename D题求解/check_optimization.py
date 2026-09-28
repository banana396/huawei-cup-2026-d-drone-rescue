# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""优化阶段指标、比较版本、优先关系与 Q1 下界核验。"""
import hashlib
import json
from math import ceil,isclose
from pathlib import Path
from d_common import load_inputs
from communication_schedule import solution_hash

ROOT=Path(__file__).resolve().parent


def read(name):return json.loads((ROOT/'结果'/name).read_text(encoding='utf-8'))
def digest(name):return hashlib.sha256((ROOT/'结果'/name).read_bytes()).hexdigest()


def main():
    _,models,boxes=load_inputs();q1=read('q1_results_v2.json');q2=read('q2_results.json');q3=read('q3_solution.json')
    issues=[];levels=['10','15','20','25','30']
    zones=sorted({b.zone for b in boxes.values()})
    lower={z:max(ceil(sum(b.kg for b in boxes.values() if b.zone==z)/max(m.max_kg for m in models.values())-1e-12),
                 ceil(sum(b.m3 for b in boxes.values() if b.zone==z)/max(m.max_m3 for m in models.values())-1e-12)) for z in zones}
    for level in levels:
        scene=q1['sensitivity'][level];safe=scene['safe_payload_kg'];rows=scene['trips'];m=scene['metrics']
        if set(safe)!=set(zones) or any(set(x)!=set(models) for x in safe.values()):issues.append(('Q1 missing safe payload',level))
        for key,actual in [('sorties',len(rows)),('energy_kwh',sum(r['energy_kwh'] for r in rows)),('operation_s',sum(r['operation_s'] for r in rows))]:
            if not isclose(m[key],actual,rel_tol=0,abs_tol=.001):issues.append(('Q1 metric',level,key))
    for a,b in zip(levels,levels[1:]):
        for z in zones:
            for mid in models:
                x=q1['sensitivity'][a]['safe_payload_kg'][z][mid];y=q1['sensitivity'][b]['safe_payload_kg'][z][mid]
                if x is not None and y is not None and y>x+1e-6:issues.append(('Q1 reserve monotonic',z,mid))
    if sum(lower.values())!=q1['sensitivity']['20']['metrics']['sorties']:issues.append(('Q1 lower bound not reached',))
    opt=q2['optimization'];cols=opt['objective_priority'];front=opt['pareto_candidates'];selected=q2['selected']
    if any(x['issues'] for x in opt['independent_checks']):issues.append(('Q2 candidate check',))
    key=lambda x:tuple(x['metrics'][c] for c in cols)
    if any(key(x)<key(selected) for x in front+[q2['merged']]):issues.append(('Q2 selected priority',))
    for i,a in enumerate(front):
        for b in front[i+1:]:
            def dominates(x,y):return all(x['metrics'][c]<=y['metrics'][c]+1e-8 for c in cols) and any(x['metrics'][c]<y['metrics'][c]-1e-8 for c in cols)
            if dominates(a,b) or dominates(b,a):issues.append(('Q2 front dominated pair',a['label'],b['label']))
    comparisons=read('q3_candidate_comparison.json')
    for c in comparisons:
        if c['solution_sha256']!=solution_hash(read(c['file'])):issues.append(('Q3 stale comparison',c['file']))
        if c['issue_count']:issues.append(('Q3 infeasible comparison',c['file']))
    official=next(c for c in comparisons if c['file']=='q3_solution.json')
    for field in ('makespan_s','weighted_lateness_s','transport_energy_kwh','relay_energy_kwh'):
        if not isclose(official['metrics'][field],read('q3_check.json')['metrics'][field],rel_tol=0,abs_tol=1e-6):issues.append(('Q3 comparison metric',field))
    for name in ('q3_interval_certificate.json','q3_margin_certificate_1db.json'):
        cert=read(name)
        if not cert['certified_all_intervals'] or cert.get('source_sha256')!=digest('q3_solution.json'):issues.append(('Q3 certificate not current',name))
    report={'status':'passed' if not issues else 'failed','issues':issues,'q1_lower_bound':sum(lower.values()),
            'q1_lower_bound_by_zone':lower,'q2_candidates':opt['unique_candidates'],'q2_front':len(front),
            'q3_compared_solutions':len(comparisons),'q3_semantic_hash':solution_hash(q3),
            'scope':'Finite candidate optimization and stated objective priorities; no global optimality claim for Q2/Q3',
            'source_sha256':{n:digest(n) for n in ('q1_results_v2.json','q2_results.json','q3_solution.json','q3_candidate_comparison.json')}}
    (ROOT/'结果'/'optimization_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(report)
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
