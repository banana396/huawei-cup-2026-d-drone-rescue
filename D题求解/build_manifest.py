# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""记录原题输入与主要输出的 SHA-256，便于赛队核查复现口径。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'2026年中国研究生数学建模竞赛赛题'/'D题'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def main():
    originals=[SOURCE/'山区洪涝灾害下无人机运输与通信协同优化.docx',
               SOURCE/'结果提交模板.xlsx',
               *sorted((SOURCE/'数据'/'无人机应急物资运输基础数据').glob('*.xlsx')),
               *SOURCE.glob('数据/**/数字高程模型数据（DEM）/*.tif')]
    results=[ROOT/'结果'/name for name in ('q1_results_v2.json','q2_results.json','q3_solution.json',
                                          'q3_check.json','q3_convergence.json','q3_interval_certificate.json',
                                          'q3_margin_certificate_1db.json',
                                          'q3_communication_schedule.json','q3_communication_check.json',
                                          'q3_boundary_guards.json','communication_bounds_check.json',
                                          'q3_candidate_comparison.json','q4_results.json',
                                          'q4_check.json','template_data.json')]
    results.append(ROOT/'outputs'/'d-question-20260924'/'结果提交模板_已填.xlsx')
    paths=originals+results
    missing=[str(p) for p in paths if not p.is_file()]
    if missing:raise FileNotFoundError(missing)
    data={'created_utc':datetime.now(timezone.utc).isoformat(),
          'note':'哈希用于检测输入/结果文件是否被改动；不证明模型正确',
          'files':{str(p.relative_to(ROOT.parent)):digest(p) for p in paths}}
    out=ROOT/'结果'/'manifest_sha256.json'
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(out,'files',len(paths))


if __name__=='__main__':main()
