"""Assemble the audit report from independently calculated evidence."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent;E=ROOT/'证据';BASE=ROOT.parent
def read(name):return json.loads((E/name).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
s=read('strict_audit_summary.json');q1=read('independent_q1_check.json');tab=read('independent_table_check.json');hp=read('high_precision_table_counterexamples.json');tests=read('negative_tests.json')
frozen=read('frozen_input_sha256.json');unchanged={p:sha(Path(p))==h for p,h in frozen.items()}
assert all(unchanged.values()),'An audited input or primary checker changed after run'
assert all(t['detected'] for t in tests)
assert all(r['mismatch_confirmed'] for r in hp)
q2=s['Q2'];q3=s['Q3'];relay=s['relay'];book=BASE/'D题优化/outputs/optimization-20260928/结果提交模板_优化版.xlsx'
decision={'strict_workbook_verdict':'NOT_ACCEPTED','reason':'Confirmed communication-state discrepancies near switching boundaries; do not interpret physical feasibility as exact workbook-state compliance.','physical_feasibility':'PASS_UNDER_DECLARED_MODEL','Q2':q2,'Q3_transport':q3,'Q3_relay':relay,'Q3_joint_makespan_s':s['joint_makespan_s'],'Q3_total_energy_kwh':q3['energy_kwh']+relay['energy_kwh'],'independent_coverage_intervals':s['frozen_relay_coverage']['counts']['certified_leaves'],'dense_sample_count':s['dense_scan']['points'],'merged_boundary_bands':len(tab['merged_boundary_bands']),'boundary_band_total_s':tab['boundary_band_total_s'],'high_precision_confirmed_points':len(hp),'workbook_unchanged':True,'workbook_sha256':sha(book),'Q3_assignment_required':'D题优化/结果/q3_solution.json','conditions':s['conditions']}
(E/'最终验收结论.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2),encoding='utf8')
counter='\n'.join(f"| {r['excel_rows'][0][0]} | {r['mission']} | {r['probe_time_s']:.12f} | {r['recorded_mode']} | {float(r['high_precision_margin_db']):.9f} | {float(r['high_precision_clearance_m']):.12g} | {r['actual_mode_high_precision']} |" for r in [hp[0],hp[3],hp[5]])
relaytable='\n'.join(f"| {r['id']} / {r['craft']} | {r['component']} | {r['ready']:.9f}–{r['end']:.9f} | {r['return']:.9f} | {r['energy']:.12f} | {100*r['soc']:.6f}% |" for r in relay['rows'])
report=f'''# 优化结果独立严格验收报告

验收日期：2026-09-28。验收对象：`D题优化/outputs/optimization-20260928/结果提交模板_优化版.xlsx`。

## 1. 最终判断

**当前 Excel 不予“全部硬约束严格通过”。** Q2 的 6374.6 s / 72.89 kWh 与 Q3 的 6512.2 s / 3.366 kWh 均可独立复算；在下述明确模型口径下，运输、能源、资源、硬时限，以及 Q3 全程至少存在一条可用链路均通过。但是通信表存在已复核的切换边界状态反例，不能把“存在可用链路”替代“表中记录路径及直连优先规则逐时刻正确”。本次没有优化数值、修改计划或修改 Excel。

**3.366 kWh 是中继能耗，绝不是 Q3 总能耗。** Q3 运输与中继合计 **{q3['energy_kwh']+relay['energy_kwh']:.12f} kWh**。

| 指标 | 独立重算值 | 结论 |
| --- | ---: | --- |
| Q2 所有运输机最晚返航 | {q2['makespan_s']:.12f} s | 对应 6374.6 s |
| Q2 总运输能耗 | {q2['energy_kwh']:.12f} kWh | 对应 72.89 kWh |
| Q2 最低返航 SOC | {q2['minimum_SOC']*100:.9f}% | 高于 20%，余量约 0.950489 个百分点 |
| Q2 最紧硬截止时间余量 | {q2['minimum_hard_deadline_slack_s']:.9f} s | 通过 |
| Q3 运输最晚返航 | {q3['makespan_s']:.12f} s | 独立核验 Q3 实际排程 |
| Q3 运输能耗 | {q3['energy_kwh']:.12f} kWh | 与 Q2 同组批路线，不同开始时刻 |
| Q3 运输最紧硬截止余量 | {q3['minimum_hard_deadline_slack_s']:.9f} s | 通过 |
| Q3 联合最晚返航 | {s['joint_makespan_s']:.12f} s | 对应 6512.2 s |
| Q3 中继总能耗 | {relay['energy_kwh']:.12f} kWh | 对应 3.366 kWh |
| Q3 中继最低返航 SOC | {relay['minimum_SOC']*100:.9f}% | 高于 20% |

Q2、Q3 均为 24 个运输架次，A/B/C 各 10/8/6；80 箱全部交付、没有重复，各类期望送达迟到均为 0。Q3 共 3 个中继架次、2 架中继实体机。

## 2. 独立性与输入

本次主检查器 `independent_audit.py` 不导入任何原求解器、原验证器或原通信证书。本次验收对照原题 DOCX 条文，检查器直接读取原始五份基础 XLSX、原始 DEM、提交工作簿。原题条文已另行提取至 `证据/原题全文提取.txt`，公式仍以原 DOCX 为准。

Q2 的组批、实体机、电池、开始时刻及交付任务全部从 Excel 重建。**官方模板没有 Q3 运输任务明细表，因此 Q3 还必须读取 `D题优化/结果/q3_solution.json` 中的运输任务决策字段。** 只使用已提交的箱号、路线、机型、实体机、电池和开始时刻等决策，旧能耗/返航/交付字段仅作对照；从原始数据重新算出航迹。未采用该文件或其他文件中的遮挡结论、覆盖判定、旧时间分段、旧证书与最小裕量。Excel 单文件不足以独立表达完整 Q3 方案，交付包必须同时保留这份运输决策及其哈希。

DEM 从 GeoTIFF 标签读取坐标原点、像元尺度和 PixelIsPoint 类型，按中心坐标转换为闭像元覆盖；所有航段遍历相交像元，拒绝越界与无效高程，采用分片常数高程。空间遮挡使用新实现的线段/闭像元相交；连续认证使用新实现的三维扫掠三角形裁剪。缓存仅在本次检查进程中由原始 DEM 新建。

冻结清单 `证据/frozen_input_sha256.json` 的全部文件在结束时哈希一致。

工作簿 SHA-256：`{sha(book)}`。

## 3. 原题硬约束逐项核验

| 原题要求 | 独立检查内容 | 结果 |
| --- | --- | --- |
| 每箱完整且仅配送一次 | 与原始 80 箱逐 ID 核对，核验实际服务区 | Q2/Q3 全覆盖、无重复 |
| 质量与装载体积上限 | 逐架次按原始单箱真实数值求和；沿途卸货更新载荷 | 通过 |
| O01 出发并返回、多点访问顺序 | 按实际箱号和服务区重建每一航段 | 通过 |
| DEM 净空与阶段速度 | 相交像元最大高程加 50 m；节点作业高度；三阶段飞行 | 通过；含中继往返 |
| 准备、装载、交接时间 | 按机型参数逐段逐箱重算交付和返航时刻 | 通过 |
| 返航至少 20% SOC | 逐航段剩余载荷能耗；逐运输/中继架次核验 | 通过，能耗公式适用条件见第 6 节 |
| 医疗期望时限、首批截止时限 | 每箱完成交接时刻不超过适用硬截止 | 全部满足 |
| 实体运输机与同型号电池库存 | 检查 ID/机型匹配、机占用与电池占用区间 | 通过，A/B/C 实体库存 4/2/2、电池库存 6/4/4 |
| 充满才可再次使用 | 从实际 SOC 独立重算两阶段充电；同电池任务与充电不重叠 | 通过；不同电池允许并行充电 |
| 中继位置、高度和建链时序 | DEM 内悬停，离地 300 m；飞抵并完成 30 s 建链后启用 | 通过；均达到高度上限，无额外高度余量 |
| 中继实体机/能源组件 | 核验 R01/R02，组件库存 6；返航后实体机周转 300 s | 通过；使用 3 个独立组件 |
| 双向预算与单跳拓扑 | 按两个方向较小门限；接入和回传须同刻有效 | 连续可用路径通过 |
| 所有爬升/巡航/下降/交接阶段连续通信 | 188 个阶段逐区间认证，含回程、服务启停边界 | 无未认证物理时间段 |
| 直连优先、表内记录路径真实有效 | 独立对 236 行逐段核验，再对边界高精度复查 | **严格不通过，反例见第 5 节** |

运输能耗证据、逐箱证据、资源占用证据分别保存在 `recomputed_legs.csv`、`recomputed_boxes.csv`、`resource_occupancy.csv`。不是只对照汇总数字。

中继重算明细：

| 架次 / 实体机 | 能源组件 | 建链完成–服务结束 (s) | 返航时刻 (s) | 能耗 (kWh) | 返航 SOC |
| --- | --- | --- | ---: | ---: | ---: |
{relaytable}

R02 第二次任务开始 {relay['rows'][2]['start']:.9f} s，第一次返航加周转完成 {relay['rows'][1]['return']+300:.9f} s，无重叠。能源组件分别核算，不用“另一组件在充电”阻止合法换组件起飞。

## 4. Q3 从原始 DEM 和通信参数重建的连续证据

原始参数：f=2400 MHz，系统损耗 3 dB，遮挡附加损耗 10 dB，灵敏度 −98 dBm，衰落裕量 8 dB。有效接收门限为 −90 dBm；运输–网关、运输–中继接入、中继回传–网关双向允许传播损耗分别为 122、116、126 dB。网关位于 O01 地面以上 20 m。重新判断“遮挡”后才加 10 dB，不把遮挡直接等同于断链。

对运动端点 P(t) 和固定通信端点 G，区间内全部视线包含在三维三角形 conv(G,P(t0),P(t1)) 中。将三角形按每个 DEM 闭像元裁剪，在裁剪多边形顶点求最小高度；严格高于地面即可证明整个区间无遮挡。否则按全程遮挡计算保守链路下界。距离使用区间经纬度及 WGS84 尺度的上下界，取最大距离作可用性充分判断。区间不能认证则二分；不能认证的叶区间必须报失败，不能用点采样替代。

完全新建时间划分，初始步长最多 20 s，遇服务启停即切分；最终 **{s['continuous']['counts']['certified_leaves']} 个区间全部认证**。再次禁止使用该运输任务在 Excel 中未列出的中继，仍全部通过，其中 1346 段按最坏遮挡通过，614 段通过三角形无遮挡证明；无需额外中继。

最小区间可用路径充分裕量 **{s['frozen_relay_coverage']['minimum_certified_margin_db']:.9f} dB**。这是一条“至少存在可用路径”的下界，**不是原表每个直连优先状态均有此裕量**。独立逐点核验最多 1 s 间隔、追加阶段端点和中继启停 ±1 μs：共 **{s['dense_scan']['points']} 点、0 个无可用链路点**；按点执行直连优先时最小有效裕量只有 **{s['dense_scan']['min_available_margin_db']:.12f} dB**。采样是旁证，全时段判断依据上述区间充分条件。

三个中继的回传裕量重算为 12.109428146、3.115716696、9.302164597 dB。证明采用浮点几何并施加向外坐标扩展和正净空门限，属于声明数字模型中的数值充分认证，未声称形式化精确算术证明，也未保证额外 1 dB 衰减或真实地形/定位扰动下可行。

## 5. Excel 通信表的严格验收失败点

236 行通信表在一般区间与重算状态一致；切换附近留下 1185 个不超过 1e-7 s 的未认证叶区间，合并后 **{len(tab['merged_boundary_bands'])} 段**。合计 **{tab['boundary_band_total_s']:.12g} s（按不同运输任务累加，并非单一公共时间轴长度）**，最大合并段约 1.364e-5 s。独立点探针发现 57 个状态差异。

进一步用 70 位 Decimal 算术重新计算航段时间、位置、逐像元视线相交及双向损耗，选择 8 点，**8 点均确认差异**。不是只因认证程序保守而未能证明。三个代表点如下；行号均为工作表 `Q3_通信保障` 的 Excel 行号：

| Excel 行 | 任务 | 反例时刻 (s) | 表中状态 | 高精度直连裕量 (dB) | 视线最低净空 (m) | 应判状态 |
| ---: | --- | ---: | --- | ---: | ---: | --- |
{counter}

第 128 行反例的直连净空约 1.794 m、裕量约 7.446 dB，按原题必须直连。第 63 行反例在视线擦地边界的另一侧，直连预算约 −0.846791 dB，表内却仍写直连；其地形净空仅约 −1.6e-9 m，因此反映数字模型的极微小边界差异，不应夸大为大范围断链。全程存在可用中继的结论仍成立。

原题没有赋予这些时刻自动豁免。若论文把边界定义为“按原始链路规则实时判断”，物理联合调度可执行；但不能将这份 Excel 的区间字面标签宣称为任意实数时刻都准确。验收要求是严格的，故保留 **NOT_ACCEPTED**。没有为了通过而增加容差、修改单元格或隐藏反例。

## 6. 模型口径与证据范围

原题明确给出 L(q)=L0−(L0−LF)(q/Q)^1.5、三阶段飞行时间、能耗分解和充电模型，但未完整给出水平与爬升能耗分项表达式。本次保留项目已声明的 E_horizontal=E_use·d/L(q)、E_climb=(m_empty+q)·9.80665·h/(3.6e6·η)，下降不另计；中继水平功率×水平时间、爬升按其 23.5 kg 总质量，悬停包含建链耗时、通信功率从建链完成计算。运输交接阶段按题设运输航段能耗模型不另加未给定的悬停功率。

距离采用经纬度直线及 WGS84 平均纬度局部尺度；地形为原始 DEM 像元分片常数，PixelIsPoint 按中心解释。中继飞行巡航海拔取悬停海拔与沿线最高地形加 50 m 的较大值，以保持端点高度与地形净空。开始时刻定义为准备开始。没有附加题目未给出的充电工位上限、中继并发用户上限或额外链路余量。因此数值验收结论必须注明以上口径，不能称为“无须任何建模假设即由原题唯一推出”。不证明目标函数全局多目标最优。

## 7. Q1/Q4 以及相反审计结果的处理

Q1 表内 18 个组批独立重算为 {q1['energy_kwh']:.12f} kWh、累计作业 {q1['cumulative_time_s']:.9f} s，最低 SOC {q1['minimum_soc']*100:.9f}%，80 箱覆盖、载荷、体积及单点往返均通过。本次没有重新求解最大安全载荷与余量敏感性，不把表内组批验收扩展为 Q1 论文所有论断均已验证。

Q4 在冻结原表通信依赖并单独认证这些中继足够后，各组资源数均与独立区间占用峰值一致。2 组总配置：运输机 A/B/C=6/2/3，电池=8/4/4，中继机=4、组件=4；相对库存缺 A 机 2、C 机 1、A 电池 2、中继机 2。3 组总配置：运输机=8/2/4，电池=9/4/5，中继机=5、组件=5；缺 A 机 4、C 机 2、A 电池 3、C 电池 1、中继机 3。组件库存为 6，两种方案均无组件短缺。跨组复制所依赖的中继任务、组内重新分配同型实体资源，仍是独立执行的解释口径，不能声称现有库存足够执行分区方案。

早期本检查器把“存在可用路径”证明自行选取的备用中继也加入 Q4 依赖，导致 3 组 G2 的资源误报。现已改为禁用原表未依赖的中继，重新从 DEM 认证全程可用，再按原关系统计；此更正只修正验收逻辑，没有改变计划或减少题目要求。

目录中的 `fresh_audit.py` 与 `证据/fresh_audit_results.json` 保留原样，未作为本次判定输入。该脚本报告 81.09 kWh、7 个全链路失败点和 895 个记录链路失败点，但存在可定位的方法问题：

1. `fresh_audit.py:547–552` 将原题明确的 3/2 载荷指数改为一次项。
2. `fresh_audit.py:556–560` 使用 η·巡航功率·爬升时间替代项目声明的质量势能/效率，属于另一假设，并非原题确认公式。
3. `fresh_audit.py:692–707` 用同编号 Q2 的开始时刻重建 Q3 位置。例如 Q2-004 开始 1560.1690781764914 s，而 Q3-004 实际开始 4128.260447881712 s，两者不可互换。
4. `fresh_audit.py:251–260` 用约 25 m 采样寻找航段最高 DEM，不能确保逐像元最大值；通信也是离散采样，不能构成全时段证明。

因此其失败汇总不足以推翻本次对正确 Q3 航迹的物理核验；但本次确实另行发现通信表边界状态缺陷，也不以驳回旧 FAIL 为理由宣布全表通过。

## 8. 可复现证据与运行

依次运行 `independent_audit.py`、`supplemental_checks.py`、`write_report.py`，或运行本目录 `reproduce.ps1`。仅写入独立验收目录，不写提交工作簿及原始数据。主检查器的无物理错误退出码不等同于全表严格通过；最终判断读取 `证据/最终验收结论.json` 中 `strict_workbook_verdict`。

几何自检覆盖平地、山脊遮挡与角点接触。负向测试主动在内存中破坏能耗、返航时间、交付时间、箱号唯一性、电池 ID 和实体机时序，6 种错误均被检出；另核验充电 0%、90%、100% 边界。输入文件均未更改。70 位反例另用独立 Decimal 实现，避免仅重复双精度同一几何函数。

核心证据：

- `证据/最终验收结论.json`：应交付的机器可读结论。
- `证据/independent_transport_and_energy.json`：运输/中继数值及最低约束余量。
- `证据/frozen_relays_continuous_coverage_leaves.csv`：限制为原表中继后的 1960 段证书。
- `证据/independent_dense_scan.json`：37129 个独立抽查点汇总。
- `证据/independent_table_check.json`：完整边界带与表内核验范围。
- `证据/high_precision_table_counterexamples.json`：8 个高精度反例、Excel 原行内容与像元索引。
- `证据/independent_q4_check.json`：逐组资源数。
- `证据/frozen_input_sha256.json` 与 `证据/最终文件清单_sha256.json`：输入与验收产物哈希。

本报告为 AI 辅助独立计算验收，不代替参赛队对模型假设及提交说明的署名复核。
'''
(ROOT/'严格验收报告.md').write_text(report,encoding='utf8')
manifest={str(p.relative_to(ROOT)):sha(p) for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.name!='最终文件清单_sha256.json'}
(E/'最终文件清单_sha256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'strict_workbook_verdict':decision['strict_workbook_verdict'],'physical_feasibility':decision['physical_feasibility'],'report':str(ROOT/'严格验收报告.md'),'unchanged':all(unchanged.values())},ensure_ascii=False))
