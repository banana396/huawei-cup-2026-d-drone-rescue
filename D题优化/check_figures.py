# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""图表来源、完整性及渲染检查记录核验；不代替人工视觉检查。"""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parent
if (ROOT/'.figure-deps').is_dir():sys.path.insert(0,str(ROOT/'.figure-deps'))
import pymupdf


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder=ROOT/'交付材料'/'figures';s=read(ROOT/'交付材料'/'补充结果.json')
    issues=[];checks=[]
    names=['01_terrain_routes','02_safe_payload','03_q2_tradeoff','04_q2_resources',
           '05_q3_resources','06_communication','07_q4_resources']
    for name in names:
        for ext in ('png','svg','pdf','data.json','text.json','collision.json','alignment.json'):
            if not (folder/f'{name}.{ext}').is_file():issues.append((name,'missing',ext))
        if issues:continue
        text=read(folder/f'{name}.text.json');collision=read(folder/f'{name}.collision.json')
        alignment=read(folder/f'{name}.alignment.json')
        if not text['auditable'] or text['minimum_found_pt']<5:issues.append((name,'PDF text floor'))
        if not collision['auditable'] or collision['summary']['fail'] or collision['summary']['warn']:issues.append((name,'collision'))
        if alignment['verdict']!='NOT APPLICABLE':issues.append((name,'expected single-panel figure'))
        with pymupdf.open(folder/f'{name}.pdf') as doc:
            page=doc[0]
            if len(doc)!=1 or abs(page.rect.width*25.4/72-180)>.01:issues.append((name,'dimensions'))
            if not page.get_text().strip():issues.append((name,'no editable PDF text'))
            width=page.rect.width*25.4/72;height=page.rect.height*25.4/72
        if '<text' not in (folder/f'{name}.svg').read_text(encoding='utf-8'):issues.append((name,'no editable SVG text'))
        checks.append({'figure':name,'width_mm':width,'height_mm':height,'min_font_pt':text['minimum_found_pt'],
                       'collision_fail':collision['summary']['fail'],'collision_warn':collision['summary']['warn'],
                       'pdf_sha256':sha(folder/f'{name}.pdf')})
    d=lambda name:read(folder/f'{name}.data.json')
    mapdata=d(names[0]);nodes={n['id']:n for n in s['nodes']};edges=set()
    for m in s['q3_missions']:
        route=['O01',*m['route'],'O01']
        edges.update(tuple(sorted((a,b))) for a,b in zip(route,route[1:]))
    if mapdata['nodes']!=s['nodes'] or set(map(tuple,mapdata['undirected_edges']))!=edges:issues.append(('map','nodes/edges'))
    if set(map(tuple,mapdata['relay_sites']))!={(r['lon'],r['lat']) for r in s['q3_relay_sorties']}:issues.append(('map','relay sites'))
    a=d(names[1]);safe=s['q1_safe_payload']['20']
    if a['kg']!=[[safe[z][m] for m in a['models']] for z in a['zones']]:issues.append(('payload','matrix'))
    if len(a['zones'])!=15 or len(a['models'])!=3:issues.append(('payload','missing categories'))
    q2=read(ROOT/'结果'/'q2_results.json');a=d(names[2])
    if a['selected']!=q2['selected']['metrics']:issues.append(('tradeoff','selected'))
    expected=[{k:v for k,v in x.items() if k!='missions'} for x in q2['optimization']['pareto_candidates']]
    if a['candidates']!=expected:issues.append(('tradeoff','candidate coverage'))
    for name,key in [(names[3],'q2_resource_occupancy'),(names[4],'q3_resource_occupancy')]:
        if d(name)['events']!=s[key]:issues.append((name,'events'))
    if d(names[5])['records']!=s['q3_communication']['records']:issues.append(('communication','records'))
    a=d(names[6]);q4=s['q4']['solutions']
    for k,field in [('2','two_groups'),('3','three_groups')]:
        if a[field]!=q4[k]['balanced_resource_priority']['total_required']:issues.append(('Q4',field))
    if a['inventory']!=q4['2']['balanced_resource_priority']['inventory']:issues.append(('Q4','inventory'))
    for path,h in read(folder/'provenance.json')['source_sha256'].items():
        if sha(ROOT/path)!=h:issues.append(('stale provenance',path))
    report=ROOT/'交付材料'/'解题报告.md'
    for img in re.findall(r'!\[[^]]*\]\(([^)]+)\)',report.read_text(encoding='utf-8')):
        if not (report.parent/img).is_file():issues.append(('missing report image',img))
    out={'status':'passed' if not issues else 'failed','issues':issues,'figures':checks,
         'scope':'Source data coverage and saved rendered-audit records; visual review remains separately documented'}
    (ROOT/'结果'/'figure_check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print('figures',len(checks),'issues',issues)
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
