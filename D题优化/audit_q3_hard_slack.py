# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""核算第三问前 15 个硬任务各波距离最早硬截止的时间余量。"""
from __future__ import annotations

import json
from pathlib import Path

from d_common import load_inputs

ROOT=Path(__file__).resolve().parent


def main():
    _,_,boxes=load_inputs()
    q3=json.loads((ROOT/'结果'/'q3_solution.json').read_text(encoding='utf-8'))
    for wave,part in enumerate((q3['transport_missions'][:8],q3['transport_missions'][8:12],
                                q3['transport_missions'][12:15]),1):
        margins=[]
        for m in part:
            for id,t in m['delivery_s'].items():
                b=boxes[id]
                if b.kind=='医疗物资':margins.append((b.expected_s-t,id,m['id'],'medical'))
                if b.first:margins.append((b.first_deadline_s-t,id,m['id'],'first'))
        print('wave',wave,'min_slack_s',min(margins))


if __name__=='__main__':main()
