# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""跨文件数值终验：要求已有完整复算证据，不把文件存在等同于物理可行。"""
import hashlib
import json
from math import isclose
from pathlib import Path
from communication_schedule import solution_hash,schedule_hash
from reproduce_solution import STEPS,OUTPUTS

ROOT=Path(__file__).resolve().parent


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result=ROOT/'结果';issues=[];evidence={}
    def expect(ok,label):
        evidence[label]=bool(ok)
        if not ok:issues.append(label)
    rep=read(result/'reproduction_check.json');work=ROOT/rep['workspace'];project=work/'D题求解'
    expect(rep['status']=='passed','independent_reproduction_passed')
    expect([s['command'] for s in rep['steps']]==STEPS and all(s['exit_code']==0 for s in rep['steps']),'all_22_rebuild_steps')
    expect({c['file'] for c in rep['comparisons']}==set(OUTPUTS),'all_12_output_comparisons')
    for c in rep['comparisons']:
        expect(c['json_equal'] and digest(ROOT/c['file'])==c['reference_sha256'] and digest(project/c['file'])==c['reproduced_sha256'],'reproduced_current:'+c['file'])
    for name,h in rep['script_sha256'].items():expect(digest(ROOT/name)==h,'reproduction_script_current:'+name)
    for name,h in rep['input_sha256'].items():expect(digest(ROOT.parent/name)==h,'input_current:'+name)
    for step in rep['steps']:
        log=ROOT/step['log'];expect(log.is_file() and log.stat().st_size>0,'step_log:'+step['command'][0])
    for name in ('q1_check.json','q2_check.json','q3_communication_check.json','communication_bounds_check.json'):
        d=read(project/'结果'/name);expect(d['status']=='passed' and not d.get('issues',[]),'rebuilt_check:'+name)
    for name in ('q3_check.json','q4_check.json'):
        d=read(project/'结果'/name);expect(d['status']=='passed_sampled_verification' and not d['issues'],'rebuilt_check:'+name)
    for name in ('q3_interval_certificate.json','q3_margin_certificate_1db.json'):
        d=read(project/'结果'/name)
        expect(d['certified_all_intervals'] and d['source_sha256']==digest(result/'q3_solution.json'),'rebuilt_certificate:'+name)
    q3=read(result/'q3_solution.json');comm=read(result/'q3_communication_schedule.json');q4=read(result/'q4_results.json')
    expect(comm['solution_sha256']==solution_hash(q3) and q4['q3_solution_sha256']==solution_hash(q3),'q3_lineage')
    expect(q4['communication_sha256']==schedule_hash(comm),'q4_frozen_communication')
    t=read(result/'template_check.json')
    expect(t['status']=='passed' and t['checked_sheets']==6 and t['checked_data_rows']==427 and t['injected_stale_q2_detected'],'six_sheet_check')
    for path,h in t['sha256'].items():expect(digest(ROOT/path)==h,'template_source_current:'+path)
    f=read(result/'figure_check.json');expect(f['status']=='passed' and len(f['figures'])==7,'seven_figures_check')
    for item in f['figures']:
        expect(digest(ROOT/'交付材料'/'figures'/f'{item["figure"]}.pdf')==item['pdf_sha256'],'figure_current:'+item['figure'])
    o=read(result/'optimization_check.json');expect(o['status']=='passed' and not o['issues'],'optimization_check')
    for name,h in o['source_sha256'].items():expect(digest(result/name)==h,'optimization_current:'+name)
    q1=read(result/'q1_results_v2.json');alt=q1['alternative_20_energy_first']
    for key,value in [('sorties',len(alt['trips'])),('energy_kwh',sum(r['energy_kwh'] for r in alt['trips'])),('operation_s',sum(r['operation_s'] for r in alt['trips']))]:
        expect(isclose(value,alt['metrics'][key],rel_tol=0,abs_tol=.001),'q1_alternative_metric:'+key)
    supplement=read(ROOT/'交付材料'/'补充结果.json');q2=read(result/'q2_results.json')
    expect(supplement['q2_missions']==q2['selected']['missions'] and supplement['q3_missions']==q3['transport_missions'],'supplement_transport_lineage')
    expect(len(supplement['q3_box_deliveries'])==80 and len({x['box'] for x in supplement['q3_box_deliveries']})==80,'supplement_q3_80_boxes')
    expect(len(supplement['q2_resource_occupancy'])==52 and len(supplement['q3_resource_occupancy'])==82,'supplement_resource_coverage')
    expect((ROOT/'交付材料'/'解题报告.md').read_bytes()==(project/'交付材料'/'解题报告.md').read_bytes(),'report_reproduced')
    for name in ('解题报告.md','图表说明.md','运行说明.md','逐项验收清单.md'):
        expect((ROOT/'交付材料'/name).is_file(),'delivery_document:'+name)
    report={'status':'passed' if not issues else 'failed','issues':issues,'evidence':evidence,
            'scope':'Numerical solution and current artifact consistency; no global optimum, real-flight validation, team signature or official submission claim',
            'human_actions':['核实实际 AI 工具版本及发布日期','队员理解与复核','按竞赛论文模板定稿、队号命名和正式提交'],
            'source_sha256':{name:digest(result/name) for name in ('reproduction_check.json','template_check.json','figure_check.json','optimization_check.json')}}
    (result/'final_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('final numerical checks',len(evidence),'issues',issues)
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
