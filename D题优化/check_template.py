# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""将导出的六张工作表逐单元格同已核验 JSON 中间数据比对。"""
from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from math import isclose
from pathlib import Path

from openpyxl import load_workbook
from d_common import load_inputs

ROOT=Path(__file__).resolve().parent
WORKBOOK=ROOT/'outputs'/'optimization-20260928'/'结果提交模板_优化版.xlsx'


def source_matrices():
    """独立从正式解读取六表，不信任填表中间文件的版本。"""
    def read(name):
        return json.loads((ROOT/'结果'/name).read_text(encoding='utf-8'))
    _,_,boxes=load_inputs()
    q1=read('q1_results_v2.json')['sensitivity']['20']['trips']
    q2=read('q2_results.json')['selected']['missions']
    q3=read('q3_solution.json')
    q4=read('q4_results.json')
    labels={'climb':'爬升','cruise':'巡航','descent':'下降','delivery':'交接'}
    expected={
        'Q1_单点组批':[[r['id'],r['zone'],r['model'],','.join(r['boxes']),r['kg'],r['m3'],r['operation_s'],r['energy_kwh'],100*r['return_soc']] for r in q1],
        'Q2_运输架次':[[r['id'],r['craft'],r['model'],r['battery'],r['start_s'],'→'.join(r['route']),r['return_s'],r['energy_kwh']] for r in q2],
        'Q2_逐箱交付':[[box,r['id'],boxes[box].zone,t] for r in q2 for box,t in r['delivery_s'].items()],
        'Q3_中继架次':[[r['id'],r['craft'],r['component'],r['start_s'],r['lon'],r['lat'],r['alt_m'],r['ready_s'],r['service_end_s'],r['return_s'],r['energy_kwh']] for r in q3['relay_sorties']],
        'Q3_通信保障':[[r['mission'],labels[r['phase']],r['start_s'],r['end_s'],r['mode'],r['relay_id']] for r in read('q3_communication_schedule.json')['records']],
        'Q4_分区配置':[],
    }
    keys=('A_craft','B_craft','C_craft','A_batteries','B_batteries','C_batteries','relay_craft','relay_components')
    for k in ('2','3'):
        for i,g in enumerate(q4['solutions'][k]['balanced_resource_priority']['groups'],1):
            expected['Q4_分区配置'].append([int(k),f'G{i}',','.join(sorted(g['zones'])),*[g['resources'][key] for key in keys]])
    return expected


def stale_matrices(data,expected):
    return [name for name in set(data)|set(expected) if data.get(name)!=expected.get(name)]


def main():
    data=json.loads((ROOT/'结果'/'template_data.json').read_text(encoding='utf-8'))
    expected=source_matrices()
    workbook=load_workbook(WORKBOOK,
                           read_only=True,data_only=True)
    mismatches=[]
    mismatches.extend(('stale source matrix',name) for name in stale_matrices(data,expected))
    if workbook.sheetnames!=list(data):mismatches.append(('sheet_names',workbook.sheetnames,list(data)))
    for name,rows in expected.items():
        if name not in workbook.sheetnames:
            mismatches.append(('missing sheet',name))
            continue
        sheet=workbook[name]
        if sheet.max_column is None:sheet.calculate_dimension(force=True)
        for i,(row,saved) in enumerate(zip(rows,sheet.iter_rows(min_row=2,max_row=len(rows)+1,
                                                              max_col=len(rows[0]),values_only=True)),2):
            for j,(want,got) in enumerate(zip(row,saved),1):
                same=isclose(got,want,rel_tol=0,abs_tol=1e-9) if isinstance(got,(int,float)) and isinstance(want,(int,float)) else (got==want or (want=='' and got is None))
                if not same:mismatches.append((name,i,j,want,got))
        for i,row in enumerate(sheet.iter_rows(min_row=len(rows)+2,values_only=True),len(rows)+2):
            if any(v is not None for v in row):mismatches.append((name,i,'unexpected trailing values'))
        if sheet.max_column>len(rows[0]):
            for i,row in enumerate(sheet.iter_rows(min_row=1,max_row=len(rows)+1,min_col=len(rows[0])+1,values_only=True),1):
                if any(v is not None for v in row):mismatches.append((name,i,'unexpected extra columns'))
    workbook.close()
    original=load_workbook(ROOT.parent/'2026年中国研究生数学建模竞赛赛题'/'D题'/'结果提交模板.xlsx',read_only=True,data_only=True)
    saved=load_workbook(WORKBOOK,read_only=True,data_only=True)
    for name,rows in expected.items():
        if name in saved.sheetnames:
            a=next(original[name].iter_rows(min_row=1,max_row=1,max_col=len(rows[0]),values_only=True))
            b=next(saved[name].iter_rows(min_row=1,max_row=1,max_col=len(rows[0]),values_only=True))
            if a!=b:mismatches.append(('header mismatch',name))
    original.close();saved.close()
    injected=deepcopy(expected)
    old=json.loads((ROOT/'结果'/'q2_results.json').read_text(encoding='utf-8'))['merged']['missions']
    injected['Q2_运输架次']=[[r['id'],r['craft'],r['model'],r['battery'],r['start_s'],'→'.join(r['route']),r['return_s'],r['energy_kwh']] for r in old]
    detected='Q2_运输架次' in stale_matrices(injected,expected)
    if not detected:mismatches.append(('injected stale Q2 not detected',))
    files=[ROOT/'结果'/name for name in ('q1_results_v2.json','q2_results.json','q3_solution.json','q3_communication_schedule.json','q4_results.json','template_data.json')]
    files.append(WORKBOOK)
    report={'status':'passed' if not mismatches else 'failed','checked_sheets':len(expected),
            'checked_data_rows':sum(map(len,expected.values())),'issues':mismatches,
            'source_policy':'Q2 selected; all six sheets compared to current formal solution files',
            'injected_stale_q2_detected':detected,
            'sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (ROOT/'结果'/'template_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('checked_sheets',len(data),'checked_data_rows',sum(map(len,data.values())),
          'mismatches',len(mismatches))
    for issue in mismatches[:10]:print(issue)
    if mismatches:raise SystemExit(1)


if __name__=='__main__':main()
