# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""论文文字稿数据与结构验收；明确不代替公式渲染、版面检查或队员确认。"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DELIVERY = ROOT / '交付材料'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(text):
    issues = []
    evidence = {}

    def expect(ok, label):
        evidence[label] = bool(ok)
        if not ok:
            issues.append(label)

    figures = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', text)
    expect(len(figures) == 7 and len(set(figures)) == 7, 'seven_distinct_figures')
    for path in figures:
        expect((DELIVERY / path).is_file(), 'figure_exists:' + path)
    expect(re.findall(r'^图 (\d+)｜', text, flags=re.M) == list(map(str, range(1, 8))), 'figure_caption_order')
    expect(re.findall(r'\\tag\{(\d+)\}', text) == list(map(str, range(1, 10))), 'nine_equation_numbers')
    expect(text.count('$$') == 18, 'display_math_delimiters')
    for heading in ('摘要', '1 问题重述与分析', '2 模型假设与适用范围', '3 符号定义与公共计算规则',
                    '4 第一问 单点运输能力与组批', '5 第二问 多点运输与共享电池调度',
                    '6 第三问 运输与通信中继联合调度', '7 第四问 固定关系分区与资源配置',
                    '8 验证与适用边界', '9 结论', '参考文献与资料', '附录 A 人工智能使用与人工复核',
                    '附录 B 结果文件与可复算程序'):
        expect('## ' + heading in text, 'section:' + heading)
    q1 = read(ROOT / '结果/q1_results_v2.json')
    for z, row in q1['sensitivity']['20']['safe_payload_kg'].items():
        expected = f'| {z} | {row["A"]:.3f} | {row["B"]:.3f} | {row["C"]:.3f} |'
        expect(expected in text, 'safe_payload_row:' + z)
    for reserve, data in q1['sensitivity'].items():
        m = data['metrics']
        expected = f'| {reserve}% | {m["sorties"]} | {m["energy_kwh"]:.6f} | {m["operation_s"]:.3f} |'
        expect(expected in text, 'reserve_row:' + reserve)
    q2 = read(ROOT / '结果/q2_results.json')
    for key, name in (('baseline', '单点基线'), ('merged', '原多点基线'), ('selected', '选择方案')):
        m = q2[key]['metrics']
        expected = f'| {name} | {m["sorties"]} | {m["energy_kwh"]:.6f} | {m["makespan_s"]:.3f} | {m["weighted_lateness_s"]:.3f} |'
        expect(expected in text, 'q2_comparison:' + key)
    summary = read(DELIVERY / '结果摘要.json')
    q3 = summary['Q3']
    n = read(ROOT / '结果/q3_neighborhood_search.json')['accepted']['metrics']
    for name, a, b, fmt in (
        ('运输架次', q3['transport_missions'], n['sorties'], 'd'),
        ('中继架次', q3['relay_sorties'], n['relay_sorties'], 'd'),
        ('总能耗/kWh', q3['transport_energy_kwh'] + q3['relay_energy_kwh'], n['total_energy_kwh'], '.6f'),
        ('联合完工/s', q3['makespan_s'], n['joint_makespan_s'], '.3f'),
        ('加权迟到/加权秒', q3['weighted_lateness_s'], n['weighted_lateness_s'], '.3f')):
        expect(f'| {name} | {a:{fmt}} | {b:{fmt}} |' in text, 'q3_tradeoff:' + name)
    for ng in ('2', '3'):
        for i, group in enumerate(summary['Q4'][ng]['groups'], 1):
            r = group['resources']
            craft = '/'.join(str(r[f'{k}_craft']) for k in 'ABC')
            battery = '/'.join(str(r[f'{k}_batteries']) for k in 'ABC')
            row = f'| {ng} 组 | G{i} | {craft} | {battery} | {r["relay_craft"]} | {r["relay_components"]} |'
            expect(row in text, f'q4_group_resources:{ng}:{i}')
    expect('0.272001%' in text and '3.241767%' in text and '17 个真实点值反例' in text, 'tradeoff_boundaries')
    for label, phrase in {
        'energy_assumption': '仍是本队采用的建模假设',
        'not_global': '不保证全局最优',
        'nominal_vs_robust': '不能称其“不可行”',
        'no_false_human_verification': '不代表队员已完成理解',
        'shared_verification_modules': '共用底层模块',
        'terrain_failure': '855 次通信中断',
        'lineage': '第四问仅继承第三问正式主方案',
        'ai_fields_not_invented': '实际模型或版本及版本发布日期尚待赛队',
        'wrong_lateness_optimum_avoided': '不是该邻域内及时性最小的方案',
    }.items():
        expect(phrase in text, label)
    expect('zhiyu' not in text and 'C:\\Users' not in text, 'no_workspace_identity_in_text')
    expect(re.findall(r'^\[(\d+)\] ', text, flags=re.M) == ['1', '2', '3', '4'], 'reference_list_numbering')
    expect(all('[' + str(i) + ']' in text.split('## 参考文献与资料')[0] + text.split('## 附录 A')[1]
               for i in range(1, 5)), 'reference_citations_present')
    expect(not re.search(r'(?m)^\|[^\n]+\|\n\n\|', text), 'markdown_tables_contiguous')
    return issues, evidence


def main():
    path = DELIVERY / '竞赛论文正文.md'
    text = path.read_text(encoding='utf-8')
    issues, evidence = check(text)
    build = read(ROOT / '结果/paper_draft_build.json')
    if build['output_sha256'] != digest(path):
        issues.append('draft_changed_since_build')
    for p, h in build['source_sha256'].items():
        if digest(ROOT / p) != h:
            issues.append('stale_source:' + p)
    if digest(ROOT / 'build_paper_draft.py') != build['builder_sha256']:
        issues.append('builder_changed')
    broken = text.replace('| 26 | 73.207637 |', '| 26 | 99.999999 |')
    detected = 'q2_comparison:selected' in check(broken)[0]
    if not detected:
        issues.append('fault_injection_not_detected')
    report = {'status': 'passed_text_checks' if not issues else 'failed', 'issues': issues,
              'evidence': evidence, 'injected_q2_number_detected': detected,
              'paper_sha256': digest(path), 'builder_sha256': digest(ROOT / 'build_paper_draft.py'),
              'abstract_characters': len(text.split('## 摘要')[1].split('关键词：')[0].strip()),
              'scope': 'Text structure and selected factual tables/qualification checks; NOT visual layout, exhaustive prose numerical proof, mathematical proof or submission approval',
              'typesetting_verified': False, 'human_disclosure_complete': False}
    (ROOT / '结果/paper_draft_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(report['status'], len(evidence), 'checks', issues, 'fault injection', detected)
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
