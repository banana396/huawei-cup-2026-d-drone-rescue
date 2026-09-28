# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""为数值切换误差带指定全区间可用的备用路径，并冻结到Q4。"""
import json

from communication_schedule import ROOT,CommunicationModel,solution_hash,schedule_hash
from diagnose_q3 import transport_phases


def inspect(data,schedule):
    model=CommunicationModel(data)
    if schedule['solution_sha256']!=solution_hash(data):raise ValueError('stale source')
    phases={m['id']:transport_phases(m,model.nodes,model.models,model.legs) for m in data['transport_missions']}
    guards=[]
    for bracket in schedule['boundary_brackets']:
        phase=phases[bracket['mission']][bracket['phase_index']]
        u,v=bracket['start_s'],bracket['end_s'];a,b=phase.at(u),phase.at(v)
        rid=None
        if model.available_interval(a,b,model.gate,'运输无人机','固定网关 G01'):
            rid=''
        else:
            for name,r in model.relays.items():
                if (r['ready_s']<=u and v<=r['service_end_s'] and model.backhaul[name]>=0 and
                        model.available_interval(a,b,model.sites[name],'运输无人机','中继接入端')):
                    rid=name;break
        if rid is None:raise RuntimeError(f'边界无整段保证路径: {bracket}')
        guards.append({**bracket,'guaranteed_relay_id':rid})
    return {'solution_sha256':solution_hash(data),'communication_sha256':schedule_hash(schedule),
            'status':'passed','guards':guards,
            'rule':'边界误差带内仍优先直连；仅在直连不可用时使用该误差带全程可用的指定中继。各组保留此备用保障关系。'}


def main():
    data=json.loads((ROOT/'结果'/'q3_solution.json').read_text(encoding='utf-8'))
    schedule=json.loads((ROOT/'结果'/'q3_communication_schedule.json').read_text(encoding='utf-8'))
    result=inspect(data,schedule)
    (ROOT/'结果'/'q3_boundary_guards.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('boundary guards',len(result['guards']),'all continuously covered')


if __name__=='__main__':main()
