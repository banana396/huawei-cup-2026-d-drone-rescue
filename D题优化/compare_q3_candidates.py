# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""对第三问软任务排序候选做同口径独立检查与指标比较。"""
from __future__ import annotations

import json
from pathlib import Path

from check_q3 import inspect
from communication_schedule import solution_hash

ROOT=Path(__file__).resolve().parent/'结果'


def main():
    files=([ROOT/'q3_solution_serial_baseline.json',ROOT/'q3_solution_fast_baseline.json',ROOT/'q3_solution.json',
            ROOT/'q3_margin_candidate_10s.json',ROOT/'q3_margin_candidate_20s.json']+
           [ROOT/f'q3_candidate_{mode}.json'
            for mode in ('ratio','weight','duration','relay_first')])
    result=[]
    for p in files:
        data=json.loads(p.read_text(encoding='utf-8'))
        issues,metrics=inspect(data,5,'exact')
        certificate=ROOT/('q3_margin_certificate_1db.json' if p.stem=='q3_solution' else f'q3_margin_certificate_1db_{p.stem}.json')
        robust=json.loads(certificate.read_text(encoding='utf-8'))['certified_all_intervals'] if certificate.exists() else None
        result.append({'file':p.name,'solution_sha256':solution_hash(data),'issue_count':len(issues),'metrics':metrics,
                       'extra_1db_certificate_passed':robust,
                       'scope':'同一名义通信口径；额外1dB抗扰结论只引用对应方案独立证书，不推及全部候选'})
        print(p.name,'issues',len(issues),'makespan',round(metrics['makespan_s'],3),
              'lateness',round(metrics['weighted_lateness_s'],3))
    (ROOT/'q3_candidate_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
