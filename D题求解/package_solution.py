# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""生成可核验交付包；不打包托管依赖、缓存或 node_modules。"""
from datetime import datetime,timezone
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slim',action='store_true',help='去除复算目录中的重复输入，生成低于50MB的ZIP候选并执行解压检查')
    args=parser.parse_args()
    for name in ('check_optimization.py','check_template.py','check_figures.py',
                 'check_q3_neighborhood.py','check_paper_draft.py','check_final.py','论文制作/check_typeset.py','check_ai_disclosure.py'):
        subprocess.run([sys.executable,'-X','utf8',str(ROOT/name)],cwd=ROOT.parent,check=True)
    required = [ROOT/'交付材料/竞赛论文正文.md', ROOT/'交付材料/第三问组批路线邻域对照.md',
                ROOT/'论文制作/artifact.md', ROOT/'论文制作/写作与证据审查.md',
                ROOT/'结果/paper_draft_check.json', ROOT/'结果/q3_neighborhood_check.json',
                ROOT/'交付材料/交付状态与剩余事项.md', ROOT/'交付材料/D题论文_排版核对稿.docx',
                ROOT/'交付材料/D题论文_排版核对稿.pdf', ROOT/'结果/paper_typeset_check.json',
                ROOT/'论文制作/visual_review_02.json']
    required += [ROOT/'结果/ai_disclosure_check.json']
    for p in required:
        if not p.is_file(): raise FileNotFoundError(f'缺少当前阶段交付物: {p}')
    paper_check=json.loads((ROOT/'结果/paper_draft_check.json').read_text(encoding='utf-8'))
    if paper_check['status']!='passed_text_checks':raise ValueError('论文文字稿检查未通过')
    typeset_check=json.loads((ROOT/'结果/paper_typeset_check.json').read_text(encoding='utf-8'))
    if typeset_check['status']!='passed_typeset_review':raise ValueError('论文排版核对未通过')
    readiness={'artifact_stage':'numerical_solution_and_typeset_review_draft',
               'submission_ready':False,'typesetting_verified':True,
               'human_disclosure_complete':paper_check['human_disclosure_complete'],
               'scope':'Includes current numerical results, 17-page visually reviewed DOCX/PDF draft, neighborhood tradeoff and reproducibility evidence. AI metadata and team approval are incomplete.',
               'remaining':['Verify actual AI tool model/version and release date','Team understanding, revision and approval',
                            'Re-render and re-review after disclosure or team edits','Confirm team-specific filename and submit manually'],
               'attachment_rules':{'max_bytes_conservative':50000000,'paper_filename':'D<team_id>.pdf',
                                   'manual_attachment_filename':'D<team_id>.rar',
                                   'format_note':'Manual prose specifies RAR, but its example upload screenshot allows ZIP/RAR. Confirm current official requirement; never rename ZIP to RAR.',
                                   'final_pdf_md5_frozen':False},
               'expected_failure':'q3_joint_candidate_001 nominal communication passes; extra 1 dB test fails and is retained as tradeoff evidence'}
    save(ROOT/'结果/delivery_readiness.json',readiness)
    versions={'python':sys.version,'numerical':{n:importlib.metadata.version(n) for n in ('numpy','Pillow','openpyxl')},
              'figure':{d.metadata['Name']:d.version for d in importlib.metadata.distributions(path=[str(ROOT/'.figure-deps')])},
              'note':'Numbers use numerical environment; figure scripts prepend local figure dependencies when present. Dependencies not bundled.'}
    save(ROOT/'结果'/'runtime_versions.json',versions)
    # 更新旧版关键文件清单，同时另建覆盖全部交付物的清单。
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'build_manifest.py')],check=True)
    paths=list(ROOT.glob('*.py'))+list(ROOT.glob('*.mjs'))+list(ROOT.glob('*.md'))
    paths+=list((ROOT/'结果').glob('*.json'))
    paths += [p for p in (ROOT/'交付材料').rglob('*') if p.is_file() and not p.name.endswith('.collision.pdf')]
    paths += [p for p in (ROOT/'论文制作').glob('*') if p.is_file() and p.suffix in ('.md','.py','.ps1','.json')]
    paths += [ROOT.parent/'附件3_论文模板_转换.docx',ROOT.parent/'附件3_论文模板_转换.pdf']
    # 带上论文规范、原始模板与 AI 规则；不收集其他赛题或无关个人文件。
    for prefix in ('附件1：','附件2：','附件3：','附件4：'):
        matches=list(ROOT.parent.glob(prefix+'*'))
        if not matches:raise FileNotFoundError(prefix)
        paths += [p for p in matches if p.is_file()]
    paths += list((ROOT/'outputs'/'d-question-20260924').glob('*.xlsx'))
    source=ROOT.parent/'2026年中国研究生数学建模竞赛赛题'/'D题'
    paths += [p for p in source.rglob('*') if p.is_file()]
    rep=json.loads((ROOT/'结果'/'reproduction_check.json').read_text(encoding='utf-8'))
    replay=ROOT/rep['workspace']
    paths += [p for p in replay.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    excluded=[]
    if args.slim:
        # 仅从新压缩包移除重复输入；原工作目录和历史复算目录保持完整。
        for name,h in rep['input_sha256'].items():
            duplicate=replay/name
            original=ROOT.parent/name
            if sha(duplicate)!=h or sha(original)!=h:
                raise ValueError(f'不能去重：复算输入与原件不一致 {name}')
            excluded.append(duplicate)
        required += [ROOT/'交付材料/提交前核对清单.md']
    manifest=ROOT/'结果'/('slim_manifest_sha256.json' if args.slim else 'delivery_manifest_sha256.json')
    package_report=ROOT/'结果'/('slim_package_check.json' if args.slim else 'package_check.json')
    # 打包证明在压缩包外，避免自引用和携带另一旧包的过期清单。
    excluded_reports={ROOT/'结果'/n for n in ('delivery_manifest_sha256.json','slim_manifest_sha256.json','package_check.json','slim_package_check.json')}
    paths=sorted(set(p for p in paths if p not in excluded_reports and p not in excluded))
    mapping={str(p.relative_to(ROOT.parent)).replace('\\','/'):sha(p) for p in paths}
    save(manifest,{'created_utc':datetime.now(timezone.utc).isoformat(),'files':mapping,
                   'deduplicated_inputs':[str(p.relative_to(ROOT.parent)).replace('\\','/') for p in excluded],
                   'note':'Exact package content hashes; does not by itself prove model correctness. Runtime caches and node_modules excluded. Slim mode keeps one complete original input set and all saved replay outputs/logs; use reproduce_solution.py to create a new replay, not the deduplicated historical replay directory.'})
    outdir=ROOT/'交付包';outdir.mkdir(exist_ok=True)
    archive=outdir/('D题附件_精简待确认_20260926.zip' if args.slim else 'D题解题材料_排版核对稿_20260926.zip')
    staging=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(staging,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in paths+[manifest]:z.write(path,str(path.relative_to(ROOT.parent)).replace('\\','/'))
    issues=[]
    with zipfile.ZipFile(staging) as z:
        bad=z.testzip()
        if bad:issues.append(('CRC',bad))
        for name,h in mapping.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=h:issues.append(('hash',name))
        if len(z.namelist())!=len(mapping)+1:issues.append(('entry count',))
        for path in required:
            if str(path.relative_to(ROOT.parent)).replace('\\','/') not in z.namelist():
                issues.append(('required artifact missing',str(path)))
        manifest_entry=str(manifest.relative_to(ROOT.parent)).replace('\\','/')
        if hashlib.sha256(z.read(manifest_entry)).hexdigest()!=sha(manifest):issues.append(('manifest hash',))
    relocated=[];extracted=None
    if args.slim:
        if staging.stat().st_size>50000000:issues.append(('size exceeds conservative 50MB',staging.stat().st_size))
        if issues:raise RuntimeError(f'打包验证失败，未替换交付包: {issues}')
        # 保留解压测试目录和日志以供审计，不删除用户文件。
        extracted=Path(tempfile.mkdtemp(prefix='slim-verify-',dir=outdir))
        with zipfile.ZipFile(staging) as z:
            for name in z.namelist():
                if not (extracted/name).resolve().is_relative_to(extracted.resolve()):
                    raise ValueError(f'Unsafe archive path: {name}')
            z.extractall(extracted)
        for name in ('check_optimization.py','check_template.py','check_q3_neighborhood.py',
                     'check_paper_draft.py','check_final.py','论文制作/check_typeset.py','check_ai_disclosure.py'):
            p=subprocess.run([sys.executable,'-X','utf8',str(extracted/'D题求解'/name)],
                             cwd=extracted,capture_output=True,encoding='utf-8')
            log=extracted/(Path(name).stem+'.log')
            log.write_text(p.stdout+'\n'+p.stderr,encoding='utf-8')
            relocated.append({'script':name,'exit_code':p.returncode,'log':str(log.relative_to(ROOT))})
            if p.returncode:issues.append(('extracted check failed',name))
            print('extracted check',name,'exit',p.returncode,flush=True)
    if issues:raise RuntimeError(f'打包验证失败，未替换交付包: {issues}')
    staging.replace(archive)
    report={'status':'passed' if not issues else 'failed','issues':issues,'files':len(mapping)+1,
            'archive':str(archive.relative_to(ROOT)),'bytes':archive.stat().st_size,'archive_sha256':sha(archive),
            'manifest_sha256':sha(manifest),'scope':'ZIP CRC and every packaged file hash verified; numerical, paper text and typeset readback checks run before packaging; team approval and AI metadata incomplete',
            'submission_ready':False,'required_current_artifacts':len(required),
            'format':'zip','size_under_50000000_bytes':archive.stat().st_size<=50000000,
            'deduplicated_input_files':len(excluded),'relocated_checks':relocated,
            'extracted_workspace':str(extracted.relative_to(ROOT)) if extracted else None,
            'relocation_scope':'Same Python runtime, new extraction directory, no numeric re-solve; existing reproduction evidence rechecked. No independent-machine claim.'}
    save(package_report,report);print(report)
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
