# D题可复算求解工作区

原题和基础数据位于上级目录 `2026年中国研究生数学建模竞赛赛题/D题`，不在此处修改。此目录包含四问的求解脚本、逐题检查器、数值结果和已填官方模板。

先读 [`模型口径.md`](模型口径.md)、[`进度.md`](进度.md) 和 [`通信鲁棒性试验.md`](通信鲁棒性试验.md)。赛题未规定水平与爬升电耗的具体分项公式；目前使用的公式是明确标注的建模假设，所有数值结论均依赖该假设。当前正式 Q3 已采用可承受额外 1 dB 链路损耗的方案；这不代表 5 m 地形/定位压力测试通过，亦不改变原题直连优先记录下极薄的名义最小裕量。

## 主要文件

| 文件 | 用途 |
| --- | --- |
| `d_common.py` | 输入解析、DEM 穿格、航段时间和电耗、运输与中继参数 |
| `verify_geometry.py` | PixelIsPoint 与地形航段的独立测试 |
| `solve_q1.py`、`check_q1.py` | 单点安全载荷、组批、余量敏感性及逐箱复核 |
| `solve_q2.py`、`optimize_q2.py`、`check_q2.py` | 多点配送基线、排序与实体分配优化及独立复核 |
| `radio.py`、`relay_flight.py` | 通信预算与中继飞行资源计算 |
| `q3_transport_seed.py`、`diagnose_q3.py`、`q3_individual_cover.py` | Q3 时序种子、直连盲区和候选中继站点 |
| `solve_q3.py`、`check_q3.py` | 运输-中继联合解与逐段通信、能量、资源复核 |
| `radio_interval.py`、`certify_q3_intervals.py`、`verify_radio_interval.py` | 通信视线连续区间充分判别、全程区间核验及随机测试 |
| `audit_q3_critical_link.py` | 输出认证裕量最小区间的直连和已在位中继备选链路裕量 |
| `audit_q3_margin.py`、`audit_q3_perturb.py` | 链路预算门槛采样筛查及地形/位置扰动压力测试 |
| `compare_q3_candidates.py`、`check_q3_convergence.py` | Q3 排序候选及采样步长对照 |
| `solve_q4.py`、`check_q4.py` | 冻结 Q3 后 2/3 组穷举配置与组内复核 |
| `prepare_template_data.py`、`fill_official_template.mjs` | 六张官方结果表的数据整理与填报 |

## 结果位置

- `结果/q1_results_v2.json`、`q2_results.json`、`q3_solution.json`、`q4_results.json`：完整数值解；`q3_solution.json` 含官方模板没有单列的 Q3 运输架次和逐箱交付。
- `结果/q3_check.json`、`q4_check.json`：逐题检查记录。
- `结果/q3_convergence.json`、`q3_interval_certificate.json`、`q3_margin_certificate_1db.json`：采样收敛、名义及额外 1 dB 链路损耗区间充分条件核验；`manifest_sha256.json`：关键输入与输出的 SHA-256。
- `结果/q3_solution_fast_baseline.json` 等 `_fast_baseline` 文件：升级前快速方案及其 Q4/模板数据归档，不用于当前提交。
- [`已填官方模板`](outputs/d-question-20260924/结果提交模板_已填.xlsx)：按照原有六张表填报，不是已经提交。
- `结果/q1_results.json` 是旧版半像元修正前对照，**勿作为论文最终数据**。

## 复现与状态

复跑顺序见 `进度.md`。依赖 Python 的 NumPy、Pillow、openpyxl；填表另需托管 Node.js 中的 `@oai/artifact-tool`。运行填表脚本前需要在 `D题求解` 目录建立指向托管 `node_modules` 的目录联接；当前保留该联接，最终交付时不打包运行时依赖。变更地形、能耗或通信口径后，须重建所有受影响结果，不能只改论文数字。

当前主要条件性指标：Q1 18 架次、59.130424 kWh；Q2 选择方案 26 架次、73.207637 kWh、最晚返航 12595.021 s、加权迟到 157921.355 s；Q3 26 个运输架次加 15 个中继架次、联合完工 24325.644 s、加权迟到 2458442.255 s；Q4 在选定的均衡方案下，2 组缺 2 架中继，3 组缺 2 架 C 型运输机、4 架中继及 1 组中继能源组件。Q3 仍继承原 Q2 多点基线的组批和访问顺序，不继承 Q2 选择方案的机型和时刻。具体分组与逐项库存差见 `q4_results.json`。`solve_q3.py` 无参数默认复现当前主方案；快速对照需显式运行 `solve_q3.py due 0`，不会覆盖正式结果。

2026-09-25 已将官方模板的 Q2 两表更新为 `selected`；`结果/template_check.json` 直接从四问正式结果重建六表期望值，而非只与中间矩阵核对。六表 427 条数据行回读无不符，旧 Q2 矩阵注入被检出。解题说明见 `交付材料/解题报告.md`，七张图已补齐并完成数据及视觉检查。该技术稿不是已经由队员签署的比赛终稿。

独立复算入口为 `python D题求解/reproduce_solution.py`：从原始输入完成 22 步，12 个关键 JSON 与正式解完全一致。`check_final.py` 的 138 项数值与文件一致性检查通过。完整说明见 `交付材料/运行说明.md`、`交付材料/逐项验收清单.md`；人工作业与程序验收范围分开列示。

通信表已改为自适应区间判别与显式数值边界，Q4 从 `q3_communication_schedule.json`、`q3_boundary_guards.json` 读取完整冻结关系。旧的 1 s 中点划分和 Q4 独立筛除中继的做法已弃用。当前解题总验收尚未完成，详见 `解题验收.md`。

程序与结果由 AI 协助生成，须由赛队逐项复核并按赛题规定披露所用工具、型号、开发机构、版本发布日期及参与环节。尚未核验的发布日应留空待查，不能臆填。
