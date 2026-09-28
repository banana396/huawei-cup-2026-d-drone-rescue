# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""在全新独立目录从原始输入复算，不复制既有数值结果、不覆盖正式解。"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parent
STEPS=[['verify_geometry.py'],['solve_q1.py'],['check_q1.py'],
       ['solve_q2.py'],['optimize_q2.py'],['check_q2.py'],
       ['q3_transport_seed.py'],['diagnose_q3.py','seed'],['q3_individual_cover.py'],
       ['solve_q3.py'],['check_q3.py'],['verify_radio_interval.py'],
       ['certify_q3_intervals.py'],['certify_q3_intervals.py','--required-margin-db','1'],
       ['communication_schedule.py'],['check_communication_schedule.py'],
       ['verify_communication_bounds.py'],['certify_communication_boundaries.py'],
       ['solve_q4.py'],['check_q4.py'],['prepare_template_data.py'],['build_solution_materials.py']]
OUTPUTS=['结果/q1_results_v2.json','结果/q2_results.json','结果/q3_transport_seed.json',
         '结果/q3_seed_direct_diagnostic.json','结果/q3_individual_cover.json',
         '结果/q3_solution.json','结果/q3_communication_schedule.json','结果/q3_boundary_guards.json',
         '结果/q4_results.json','结果/template_data.json','交付材料/补充结果.json','交付材料/结果摘要.json']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--list',action='store_true');args=parser.parse_args()
    if args.list:
        for s in STEPS:print('python D题求解/'+' '.join(s))
        return
    parent=ROOT/'复现验证';parent.mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='run-',dir=parent));project=work/'D题求解';project.mkdir()
    source=ROOT.parent/'2026年中国研究生数学建模竞赛赛题'/'D题'
    target=work/'2026年中国研究生数学建模竞赛赛题'/'D题'
    shutil.copytree(source,target)
    scripts=sorted(ROOT.glob('*.py'))
    for script in scripts:shutil.copy2(script,project/script.name)
    # 该目录创建时没有结果文件。所有候选和解必须由本次运行生成。
    inputs={str(p.relative_to(work)):digest(p) for p in target.rglob('*') if p.is_file()}
    sources={s.name:digest(s) for s in scripts}
    report={'status':'running','created_utc':datetime.now(timezone.utc).isoformat(),
            'workspace':str(work.relative_to(ROOT)),'python':sys.version,'steps':[],
            'input_sha256':inputs,'script_sha256':sources,'comparisons':[],
            'scope':'Fresh numerical Q1-Q4 pipeline including relay candidate search, all current communication records and template matrices; workbook export and figure rendering have separate checks'}
    report_path=ROOT/'结果'/'reproduction_check.json';save(report_path,report)
    logs=work/'logs';logs.mkdir()
    print('isolated workspace',work,flush=True)
    for index,step in enumerate(STEPS,1):
        start=time.monotonic();log=logs/f'{index:02d}-{Path(step[0]).stem}.log'
        print('START',index,'/'.join([str(len(STEPS)),*step]),flush=True)
        with log.open('w',encoding='utf-8') as stream:
            result=subprocess.run([sys.executable,'-u','-X','utf8',str(project/step[0]),*step[1:]],
                                  cwd=work,stdout=stream,stderr=subprocess.STDOUT)
        item={'command':step,'exit_code':result.returncode,'duration_s':round(time.monotonic()-start,3),
              'log':str(log.relative_to(ROOT))}
        report['steps'].append(item)
        print('END',index,'exit',result.returncode,'seconds',item['duration_s'],flush=True)
        if result.returncode:
            report['status']='failed';save(report_path,report)
            print(log.read_text(encoding='utf-8')[-5000:],flush=True);raise SystemExit(1)
        save(report_path,report)
    for rel in OUTPUTS:
        expected=ROOT/rel;actual=project/rel
        same=actual.is_file() and expected.is_file() and json.loads(actual.read_text(encoding='utf-8'))==json.loads(expected.read_text(encoding='utf-8'))
        report['comparisons'].append({'file':rel,'json_equal':same,'reference_sha256':digest(expected) if expected.exists() else None,
                                      'reproduced_sha256':digest(actual) if actual.exists() else None})
    # 防止检查期间源代码或原始输入变化而把跨版本比较标为通过。
    source_unchanged=all(digest(ROOT/name)==h for name,h in sources.items())
    inputs_unchanged=all(digest(ROOT.parent/rel)==h for rel,h in inputs.items())
    report['source_unchanged']=source_unchanged;report['inputs_unchanged']=inputs_unchanged
    report['status']='passed' if source_unchanged and inputs_unchanged and all(x['json_equal'] for x in report['comparisons']) else 'failed'
    save(report_path,report);save(work/'reproduction_check.json',report)
    print('REPRODUCTION',report['status'],report['comparisons'],flush=True)
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
