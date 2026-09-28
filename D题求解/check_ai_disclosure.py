# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""Audit disclosure header coverage; never certify actual model identity or team approval."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED = ('本程序及代码是在人工智能工具辅助下完成', 'OpenAI Codex', '模型/版本', '版本颁布日期', '开发机构：OpenAI')


def inspect_header(source):
    # Require a comment before executable statements, not a keyword buried in code.
    lines = source.lstrip('\ufeff').splitlines()
    comments = []
    for line in lines:
        if not line.strip():
            continue
        if not line.lstrip().startswith(('#', '//')):
            break
        comments.append(line)
    header = '\n'.join(comments)
    return {'missing_fields': [s for s in REQUIRED if s not in header],
            'contains_unverified_placeholder': any(s in header for s in ('待核实', '待赛队', '待确认'))}


def main():
    replay = ROOT / json.loads((ROOT/'结果/reproduction_check.json').read_text(encoding='utf-8'))['workspace']
    paths = [p for p in ROOT.iterdir() if p.suffix in ('.py', '.mjs')]
    paths += [p for p in (ROOT/'论文制作').iterdir() if p.suffix in ('.py', '.ps1')]
    paths += [p for p in replay.rglob('*') if p.suffix in ('.py', '.mjs', '.ps1') and '__pycache__' not in p.parts]
    findings = {}
    for path in sorted(set(paths)):
        findings[path.relative_to(ROOT).as_posix()] = dict(
            inspect_header(path.read_text(encoding='utf-8-sig')),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    missing = [n for n, r in findings.items() if r['missing_fields']]
    unresolved = [n for n, r in findings.items() if r['contains_unverified_placeholder']]
    # A well-shaped header with a placeholder is NOT complete disclosure.
    example = '# 本程序及代码是在人工智能工具辅助下完成。工具：OpenAI Codex；模型/版本和版本颁布日期：待核实；开发机构：OpenAI。'
    tests = {
        'missing_header_detected': bool(inspect_header('print(1)')['missing_fields']),
        'buried_header_rejected': bool(inspect_header('print(1)\n'+example)['missing_fields']),
        'placeholder_not_complete': inspect_header(example)['contains_unverified_placeholder'],
    }
    coverage_ok = not missing and all(tests.values())
    report = {
        'status': 'headers_present_metadata_unverified' if coverage_ok else 'missing_header_or_test_failure',
        'header_coverage_passed': coverage_ok,
        'checked_source_files': len(findings), 'missing_header_files': missing,
        'placeholder_files': unresolved,
        'actual_model_metadata_verified': False,
        'team_understanding_confirmed': False, 'submission_ready': False,
        'fault_injections': tests, 'files': findings,
        'scope': 'Source comment coverage only. Placeholder removal is not evidence of a true model/version/release date; verify actual usage records separately. Includes saved replay source copies, excludes third-party runtime dependencies.',
    }
    (ROOT/'结果/ai_disclosure_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('files','placeholder_files')}, ensure_ascii=False))
    raise SystemExit(not coverage_ok)


if __name__ == '__main__':
    main()
