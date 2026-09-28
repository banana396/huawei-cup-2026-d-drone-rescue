# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""Q3 轨迹时间步与通信视线步长的收敛性记录；不是连续证明。"""
from __future__ import annotations

import json
from pathlib import Path

from check_q3 import inspect

ROOT=Path(__file__).resolve().parent


def main():
    data=json.loads((ROOT/'结果'/'q3_solution.json').read_text(encoding='utf-8'))
    runs=[]
    for time_step,pixel_step in [(5,.4),(1,.4),(.25,.4),(1,.1),(1,'exact')]:
        issues,metrics=inspect(data,time_step,pixel_step)
        runs.append({'time_step_s':time_step,'pixel_step':pixel_step,
                     'issue_count':len(issues),'issues':issues,'metrics':metrics})
        print(time_step,pixel_step,'issues',len(issues),'samples',metrics['samples'],
              'blind',metrics['direct_blind_samples'])
    out={'note':'有限时间/空间采样收敛诊断，不等于严格连续时间证明','runs':runs}
    (ROOT/'结果'/'q3_convergence.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(x['issue_count'] for x in runs):raise SystemExit(1)


if __name__=='__main__':main()
