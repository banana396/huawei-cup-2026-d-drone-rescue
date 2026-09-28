# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""把已核验的四问结果整理为官方六张表的数据矩阵。"""
from __future__ import annotations

import json
from math import ceil
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources,make_leg
from diagnose_q3 import transport_phases
from radio import Position,direct,relay_path
from communication_schedule import solution_hash,schedule_hash,LABELS

ROOT=Path(__file__).resolve().parent
RESULT=ROOT/'结果'


def main():
    nodes,models,boxes=load_inputs();res=load_resources();terrain=Terrain()
    q1=json.loads((RESULT/'q1_results_v2.json').read_text(encoding='utf-8'))['sensitivity']['20']['trips']
    q2=json.loads((RESULT/'q2_results.json').read_text(encoding='utf-8'))['selected']['missions']
    q3=json.loads((RESULT/'q3_solution.json').read_text(encoding='utf-8'))
    q4=json.loads((RESULT/'q4_results.json').read_text(encoding='utf-8'))
    rows={}
    rows['Q1_单点组批']=[[r['id'],r['zone'],r['model'],','.join(r['boxes']),r['kg'],r['m3'],
                         r['operation_s'],r['energy_kwh'],100*r['return_soc']] for r in q1]
    rows['Q2_运输架次']=[[r['id'],r['craft'],r['model'],r['battery'],r['start_s'],
                         '→'.join(r['route']),r['return_s'],r['energy_kwh']] for r in q2]
    rows['Q2_逐箱交付']=[[i,r['id'],boxes[i].zone,t] for r in q2 for i,t in r['delivery_s'].items()]
    rows['Q3_中继架次']=[[r['id'],r['craft'],r['component'],r['start_s'],r['lon'],r['lat'],
                         r['alt_m'],r['ready_s'],r['service_end_s'],r['return_s'],r['energy_kwh']]
                        for r in q3['relay_sorties']]
    communication=json.loads((RESULT/'q3_communication_schedule.json').read_text(encoding='utf-8'))
    if communication['solution_sha256']!=solution_hash(q3) or q4.get('q3_solution_sha256')!=solution_hash(q3):
        raise ValueError('Q3/Q4/通信记录版本不一致')
    if q4.get('communication_sha256')!=schedule_hash(communication):raise ValueError('Q4未冻结当前通信记录')
    # 保留数值求解精度；显示小数位不改变实际单元格数值。
    rows['Q3_通信保障']=[[r['mission'],LABELS[r['phase']],r['start_s'],r['end_s'],r['mode'],r['relay_id']]
                         for r in communication['records']]
    q4rows=[]
    for k in ('2','3'):
        for idx,g in enumerate(q4['solutions'][k]['balanced_resource_priority']['groups'],1):
            n=g['resources']
            q4rows.append([int(k),f'G{idx}',','.join(sorted(g['zones'])),
                           n['A_craft'],n['B_craft'],n['C_craft'],
                           n['A_batteries'],n['B_batteries'],n['C_batteries'],
                           n['relay_craft'],n['relay_components']])
    rows['Q4_分区配置']=q4rows
    expected={'Q1_单点组批':len(q1),'Q2_运输架次':len(q2),'Q2_逐箱交付':len(boxes),'Q3_中继架次':len(q3['relay_sorties']),'Q4_分区配置':5}
    for name,count in expected.items():
        if len(rows[name])!=count:raise RuntimeError(f'{name}行数不符 {len(rows[name])}!={count}')
    path=RESULT/'template_data.json'
    path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(path,{k:len(v) for k,v in rows.items()})


if __name__=='__main__':main()
