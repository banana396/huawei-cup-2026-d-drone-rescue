# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""以独立逐格点计算反查新引入的距离下界、连续遮挡及状态充分条件。"""
import json
import random

from communication_schedule import ROOT,CommunicationModel,min_distance_m,blocked_interval,solution_hash
from diagnose_q3 import transport_phases
from radio import direct


def main():
    data=json.loads((ROOT/'结果'/'q3_solution.json').read_text(encoding='utf-8'))
    model=CommunicationModel(data);rng=random.Random(20260924)
    phases=[p for m in data['transport_missions'] for p in
            transport_phases(m,model.nodes,model.models,model.legs)]
    counts={'intervals':0,'point_comparisons':0,'blocked_certificates':0,'on_certificates':0,'off_certificates':0}
    issues=[]
    for i in range(500):
        p=rng.choice(phases);u=rng.uniform(p.t0,p.t1);v=min(p.t1,u+rng.choice([.0001,.01,.1,1,10,100]))
        a,b=p.at(u),p.at(v);lower=min_distance_m(a,b,model.gate)
        blocked=blocked_interval(a,b,model.gate,model.terrain)
        on=model.available_interval(a,b,model.gate,'运输无人机','固定网关 G01')
        off=model.direct_unavailable_interval(a,b)
        counts['intervals']+=1;counts['blocked_certificates']+=blocked
        counts['on_certificates']+=on;counts['off_certificates']+=off
        for k in range(21):
            t=u+(v-u)*k/20;r=direct(p.at(t),model.nodes,model.terrain,model.radio,'exact')
            counts['point_comparisons']+=1
            if lower>r['distance_km']*1000+1e-8:issues.append(('distance lower bound',i,t))
            if blocked and r['clearance_m']>=0:issues.append(('false blockage proof',i,t))
            if on and not r['available']:issues.append(('false availability proof',i,t))
            if off and r['available']:issues.append(('false unavailability proof',i,t))
    result={'status':'passed' if not issues else 'failed','seed':20260924,'counts':counts,'issues':issues,
            'solution_sha256':solution_hash(data),'scope':'独立点值反查，非对全部输入的形式化证明'}
    (ROOT/'结果'/'communication_bounds_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(result)
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
