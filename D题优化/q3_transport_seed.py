# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""第三问运输时间种子：按硬时限分波推迟出发，为中继周转留出窗口。"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from d_common import charging_time_s,load_inputs,load_resources
from solve_q2 import hard_deadline


ROOT=Path(__file__).resolve().parent


def main():
    _,models,boxes=load_inputs();resources=load_resources()
    source=json.loads((ROOT/'结果'/'q2_results.json').read_text(encoding='utf-8'))['merged']['missions']
    craft_available=defaultdict(float); battery_available=defaultdict(float)
    output=[]
    for r in source:
        deadlines=[hard_deadline(boxes[i]) for stop in r['stops'] for i in stop['boxes']]
        due=min(deadlines)
        target=15 if due<=3600 else 2350 if due<=7200 else 5000 if due<=10800 else 9000
        start=max(target,craft_available[r['craft']],battery_available[r['battery']])
        delta=start-r['start_s']
        new=dict(r)
        new['id']=r['id'].replace('Q2-','Q3-')
        new['start_s']=round(start,6)
        new['return_s']=round(r['return_s']+delta,6)
        new['delivery_s']={i:round(t+delta,6) for i,t in r['delivery_s'].items()}
        mid=r['model'];soc=r['return_soc']
        new['battery_recharged_s']=round(new['return_s']+charging_time_s(soc,resources.transport_batteries[mid][1]),6)
        for i,t in new['delivery_s'].items():
            b=boxes[i]
            if b.kind=='医疗物资' and t>b.expected_s+1e-7:raise RuntimeError(f'医疗超时: {i}, {t}')
            if b.first and t>b.first_deadline_s+1e-7:raise RuntimeError(f'首批超时: {i}, {t}')
        craft_available[r['craft']]=new['return_s']
        battery_available[r['battery']]=new['battery_recharged_s']
        output.append(new)
    path=ROOT/'结果'/'q3_transport_seed.json'
    path.write_text(json.dumps({'note':'通信尚未核验的时间种子，不是第三问可行方案','missions':output},ensure_ascii=False,indent=2),encoding='utf-8')
    print(path,'missions',len(output),'return',max(x['return_s'] for x in output))
    print('hard_starts',[(r['id'],r['start_s']) for r in output if any(hard_deadline(boxes[i])<float('inf') for stop in r['stops'] for i in stop['boxes'])])


if __name__=='__main__':main()
