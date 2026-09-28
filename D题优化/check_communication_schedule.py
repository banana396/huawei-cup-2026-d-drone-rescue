# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""核对通信记录覆盖、直连优先、指定中继与显式微小边界。

独立逐格链路计算检查区间内密采样、两端邻域及边界本身；并重新验证
合并记录除边界误差带以外的连续区间充分条件。
"""
import json
from collections import defaultdict
from math import ceil

from communication_schedule import ROOT,CommunicationModel,solution_hash,schedule_hash,TIME_TOL
from diagnose_q3 import transport_phases
from radio import direct,relay_path


def inspect(data,schedule,continuous=True):
    issues=[];model=CommunicationModel(data);tested=0;certified=0;boundary_samples=0
    if schedule['solution_sha256']!=solution_hash(data):issues.append('stale Q3 source')
    rows=defaultdict(list);brackets=defaultdict(list)
    for row in schedule['records']:rows[row['mission'],row['phase_index']].append(row)
    for b in schedule['boundary_brackets']:
        if not (0<b['end_s']-b['start_s']<=TIME_TOL*1.001):issues.append(('wide boundary',b))
        brackets[b['mission'],b['phase_index']].append((b['start_s'],b['end_s']))
    expected=set()
    for mission in data['transport_missions']:
        for index,phase in enumerate(transport_phases(mission,model.nodes,model.models,model.legs)):
            key=(mission['id'],index);expected.add(key)
            rr=rows[key];bb=brackets[key]
            if not rr or abs(rr[0]['start_s']-phase.t0)>1e-9 or abs(rr[-1]['end_s']-phase.t1)>1e-9:
                issues.append(('phase coverage',key));continue
            for prior,row in zip(rr,rr[1:]):
                if abs(prior['end_s']-row['start_s'])>1e-9:issues.append(('gap/overlap',key))
            for row in rr:
                u,v=row['start_s'],row['end_s'];state=(row['mode'],row['relay_id'])
                if row['phase']!=phase.kind or v<=u:issues.append(('phase/interval',row));continue
                n=max(1,ceil((v-u)/.25))
                times={u+(v-u)*k/n for k in range(1,n)}
                times.add((u+v)/2)
                times.update(t for d in (1e-5,.001,.01) for t in (u+d,v-d) if u<t<v)
                for t in sorted(times):
                    tested+=1;p=phase.at(t)
                    if any(a-1e-10<=t<=b+1e-10 for a,b in bb):
                        boundary_samples+=1;model.point_state(phase,t);continue
                    dl=direct(p,model.nodes,model.terrain,model.radio,'exact')
                    if state[0]=='直连':valid=dl['available']
                    elif state[1] in model.relays:
                        r=model.relays[state[1]]
                        valid=(not dl['available'] and r['ready_s']<=t<=r['service_end_s'] and
                               relay_path(p,model.sites[state[1]],model.nodes,model.terrain,
                                          model.radio,'exact')['available'])
                    else:valid=False
                    if not valid and len(issues)<100:issues.append(('wrong assigned state',key,t,state))
                if continuous:
                    pieces=[(u,v)]
                    for a,b in bb:
                        pieces=[piece for lo,hi in pieces for piece in
                                ([(lo,hi)] if b<=lo or hi<=a else
                                 ([(lo,a)] if lo<a else [])+([(b,hi)] if b<hi else []))]
                    stack=list(pieces)
                    checks=0
                    while stack:
                        checks+=1
                        if checks>100000:
                            raise RuntimeError(f'区间复核未收敛: {key}, {row}')
                        a,b=stack.pop()
                        if model.certify_state(phase,a,b,state):certified+=1;continue
                        if b-a<1e-9:
                            issues.append(('uncertified outside boundary',key,a,b,state));break
                        mid=(a+b)/2;stack.extend(((a,mid),(mid,b)))
            for a,b in bb:
                if a<phase.t0 or b>phase.t1:issues.append(('boundary outside phase',key))
                for t in (a,(a+b)/2,b):
                    model.point_state(phase,t);boundary_samples+=1
        print('checked',mission['id'],'points',tested,'issues',len(issues),flush=True)
    if set(rows)!=expected:issues.append('unexpected phase records')
    return {'issues':issues,'point_checks':tested,'certified_intervals':certified,
            'boundary_point_checks':boundary_samples,'records':len(schedule['records']),
            'boundary_brackets':len(schedule['boundary_brackets']),
            'boundary_total_duration_s':sum(b-a for bb in brackets.values() for a,b in bb)}


def main():
    data=json.loads((ROOT/'结果'/'q3_solution.json').read_text(encoding='utf-8'))
    schedule=json.loads((ROOT/'结果'/'q3_communication_schedule.json').read_text(encoding='utf-8'))
    result=inspect(data,schedule)
    # 破坏第一个记录的路径。只能在内存中测试，不更改方案。
    bad=json.loads(json.dumps(schedule));bad['records'][0]['mode']='中继';bad['records'][0]['relay_id']='INVALID'
    result['injected_invalid_relay_detected']=bool(inspect(data,bad,continuous=False)['issues'])
    result['status']='passed' if not result['issues'] and result['injected_invalid_relay_detected'] else 'failed'
    result['solution_sha256']=solution_hash(data)
    result['communication_sha256']=schedule_hash(schedule)
    (ROOT/'结果'/'q3_communication_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    if result['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
