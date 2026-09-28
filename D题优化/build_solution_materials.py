# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""从当前结果生成可审阅的解题报告与模板未单列的补充数据。"""
import json
from dataclasses import asdict
from math import ceil
from pathlib import Path

from d_common import Terrain,load_inputs,load_resources,make_leg
from diagnose_q3 import transport_phases
from communication_schedule import solution_hash
from optimize_q2 import metrics

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'交付材料'


def load(name):return json.loads((ROOT/'结果'/name).read_text(encoding='utf-8'))


def occupancy(missions,relays,res):
    events=[]
    for m in missions:
        events.extend([{'kind':'transport_craft','resource':m['craft'],'mission':m['id'],
                        'start_s':m['start_s'],'end_s':m['return_s']},
                       {'kind':'transport_battery','resource':m['battery'],'mission':m['id'],
                        'start_s':m['start_s'],'end_s':m['battery_recharged_s'],'return_s':m['return_s']}])
    for r in relays:
        events.extend([{'kind':'relay_craft','resource':r['craft'],'mission':r['id'],
                        'start_s':r['start_s'],'end_s':r['return_s']+res.relay_models['R'].turnaround_s},
                       {'kind':'relay_component','resource':r['component'],'mission':r['id'],
                        'start_s':r['start_s'],'end_s':r['component_recharged_s'],'return_s':r['return_s']}])
    return events


def main():
    OUT.mkdir(exist_ok=True)
    nodes,models,boxes=load_inputs();res=load_resources();terrain=Terrain()
    q1=load('q1_results_v2.json');q2=load('q2_results.json');q3=load('q3_solution.json');q4=load('q4_results.json')
    comm=load('q3_communication_schedule.json');guards=load('q3_boundary_guards.json')
    m1=q1['sensitivity']['20']['metrics'];m2=q2['selected']['metrics'];m3=load('q3_check.json')['metrics']
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    lower={z:max(ceil(sum(b.kg for b in boxes.values() if b.zone==z)/max(m.max_kg for m in models.values())-1e-12),
                     ceil(sum(b.m3 for b in boxes.values() if b.zone==z)/max(m.max_m3 for m in models.values())-1e-12))
           for z in sorted(q1['zones'])}
    q3deliveries=[{'box':i,'mission':m['id'],'zone':boxes[i].zone,'delivery_s':t,
                   'expected_s':boxes[i].expected_s,'first':boxes[i].first,'priority':boxes[i].priority}
                  for m in q3['transport_missions'] for i,t in m['delivery_s'].items()]
    supplement={'units':{'time':'s since task start','energy':'kWh','mass':'kg','volume':'m3','margin':'dB'},
                'nodes':[asdict(n) for n in nodes.values()],
                'q1_safe_payload':{k:v['safe_payload_kg'] for k,v in q1['sensitivity'].items()},
                'q1_sortie_lower_bound_by_zone':lower,
                'q2_selected_metrics':m2,'q2_missions':q2['selected']['missions'],
                'q2_resource_occupancy':occupancy(q2['selected']['missions'],[],res),
                'q3_solution_sha256':solution_hash(q3),'q3_missions':q3['transport_missions'],
                'q3_box_deliveries':q3deliveries,'q3_relay_sorties':q3['relay_sorties'],
                'q3_resource_occupancy':occupancy(q3['transport_missions'],q3['relay_sorties'],res),
                'q3_flight_phases':[asdict(p) for m in q3['transport_missions'] for p in
                                    transport_phases(m,nodes,models,legs)],
                'q3_communication':comm,'q3_boundary_guards':guards,
                'q4':q4}
    (OUT/'补充结果.json').write_text(json.dumps(supplement,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 山区洪涝灾害下无人机运输与通信协同优化：解题报告','',
           '本报告依据题面、五份基础数据、30 m 高程数据和当前可运行程序生成。数值是给定标准测试场景与下述模型假设下的结果，未作真实飞行验证。程序和本文由 AI 辅助完成；赛队提交前需核对并按规定披露，本文不代表已完成队员签署或系统提交。','',
           '## 1 任务、数据和统一口径','',
           f'场景包含 1 个调度中心 O01、15 个服务区、{len(boxes)} 个不可拆货箱，总质量 {sum(b.kg for b in boxes.values()):.0f} kg。运输机 A/B/C 分别有 4/2/2 架，共享电池分别有 6/4/4 组；中继机 2 架，能源组件 6 组。每个货箱必须且只能交付一次。医疗期望时刻和首批截止时刻是硬约束，其余期望时刻用于及时性评价。','',
           '| 符号 | 定义与单位 |','| --- | --- |',
           '| q、Q_g | 航段剩余载荷、机型最大载荷，kg |',
           '| L_g(q)、d_ij | 等效航程、水平航段距离，m |',
           '| E_g、E_p | 单组电池可用能量、架次能耗，kWh |',
           '| ρ、SOC | 返航安全余量、荷电状态，无量纲比例 |',
           '| t_i、d_i、w_i | 货箱交接完成时刻、期望时刻、优先级权重 |',
           '| T、W | 全部返航最晚时刻、加权迟到，s |','',
           '经纬度转像元时按 GeoTIFF PixelIsPoint 将 tiepoint 视为像元中心。沿两节点经纬度直线穿过所有接触像元，取最高地面海拔加 50 m 为运输航段巡航海拔。服务区作业海拔取节点表地面海拔加 30 m，O01 取节点地面海拔；每到一站完成投送后重新爬升。水平距离按两端平均纬度的局部 WGS84 椭球尺度计算，与取地形的直线轨迹一致。','',
           '按题给等效航程关系，L_g(q)=L_g0−(L_g0−L_gF)(q/Q_g)^(3/2)。航段时间为 h_up/v_up+d/v_cruise+h_down/v_down。本队采用 E_h=E_g·d/L_g(q)、E_up=(m_empty+q)g·h_up/(3.6×10^6η)；下降不额外计能耗。题面给出了能耗分解，但没有明确给出以上两个分式，因此将其作为显式建模假设，绝对数值结论依赖这一口径。不得把它们描述为专家确认的公式。','',
           '架次能耗按逐站卸载后的剩余载荷求和，并计空载返程，要求 E_p≤(1−ρ)E_g。准备、逐箱装载、飞行、基础及逐箱交接均计入时间。同站同架次货箱保守地记为该站全部交接完成时同时送达。共享电池初始满电，返航后按题给两阶段规则充满才复用：SOC<90% 时，充电时间为 T_full[0.65(0.90−SOC)/0.90+0.35]；否则为 T_full·0.35(1−SOC)/0.10。不同电池可并行充电。','',
           '## 2 第一问：最大安全载荷和组批','',
           '先对各服务区、各机型利用能耗对载荷的单调关系二分求安全质量上界。该上界是连续质量能力，不等于实际货箱能凑出的装载质量。然后枚举该服务区货箱子集与机型，剔除超重、超体积、能量不足的候选。用状态为已交付货箱集合的动态规划求集合划分，禁止跨区组批。主方案按“架次数、总能耗、累计作业时间”字典序优化；累计作业时间是各架次时间求和，不是并行完工时间。','',
           f'20% 返航余量下，主方案为 {m1["sorties"]} 架次、{m1["energy_kwh"]:.6f} kWh、累计作业 {m1["operation_s"]:.3f} s。按每区质量/体积除以最大机型容量并向上取整相加，架次数下界为 {sum(lower.values())}，与所得架次数'+('相同，故该条件下架次数最少。' if sum(lower.values())==m1['sorties'] else '不同，不能仅由该下界证明最少。'),' ',
           '能耗优先对照为 19 架次、59.033043 kWh，即增加 1 架次换取约 0.097381 kWh 节能。两种方案明确展示了架次数与电耗之间的取舍。','',
           '| 返航余量 | 架次数 | 能耗/kWh | 累计作业时间/s |','| --- | ---: | ---: | ---: |']
    for level,v in q1['sensitivity'].items():
        m=v['metrics'];lines.append(f'| {level}% | {m["sorties"]} | {m["energy_kwh"]:.6f} | {m["operation_s"]:.3f} |')
    lines+=['','所有 15×3 组安全载荷及五档变化见补充结果。升高余量使可用电量下降，某些满批组合失去可行性，25% 和 30% 时分别增至 19、20 架次。','',
            '## 3 第二问：多点运输及实体资源调度','',
            '以每区硬时限货箱优先组批，其余货箱先按第一问方法组批，再尝试最多三站的多点合并及访问顺序排列。用实际剩余载荷评估合并节能，保留满足单架次能量和时限条件的合并，形成 26 架次多点基线。随后在该组批基础上比较 5 种软任务排序、3 种飞机/电池选择准则，并从每种准则的较好起点执行两两交换邻域搜索。每次分配必须同时满足具体实体机可用、同机型电池已充满以及全部硬时限。','',
            '全局候选评价优先最小化 W=Σ_nonmedical w_i·max(0,t_i−d_i)，再比较 T、运输能耗和架次数。候选生成中的贪心分配准则不等于全局目标；例如先选节能机型可能通过减少充电占用改善后续及时性。此算法是分解启发式，不是所有组批、路径和排程的全局最优证明。','',
            '| 方案 | 架次数 | 能耗/kWh | 最晚返航/s | 加权迟到/s |','| --- | ---: | ---: | ---: | ---: |']
    for label,field in [('单点基线','baseline'),('原多点基线','merged'),('选择方案','selected')]:
        m=q2[field]['metrics'];lines.append(f'| {label} | {m["sorties"]} | {m["energy_kwh"]:.6f} | {m["makespan_s"]:.3f} | {m["weighted_lateness_s"]:.3f} |')
    lines+=['',f'共评估 {q2["optimization"]["unique_candidates"]} 个不同候选，保留 {len(q2["optimization"]["pareto_candidates"])} 组不同指标的非支配候选。选择方案的医疗迟交与首批迟交均为 0；逐箱、载荷、能量、充电和实体冲突检查通过。9 组非支配候选只代表本次搜索所得集合，不是完整 Pareto 前沿。','',
            '## 4 第三问：通信约束下运输和中继协同','',
            '第三问从第二问原多点组批基线继承货箱与访问顺序，独立构造运输波次及中继排程；不直接继承第二问选择方案的机型与送达时刻。先计算各运输阶段的直连盲区，在服务区上空、区间中点及网格位置构造中继候选，检查回传、接入、飞行净空和能源；再安排中继位置、海拔、往返时刻、服务区间、实体机及能源组件，并联动调整运输开始时刻。软任务比较按期望时刻、权重、时长等排序。','',
            '双向链路允许损耗取两个方向预算的较小值；传播损耗为 32.45+20log10(f_MHz)+20log10(D_km)+I_obstructed·L_obs，其中 D 是同一时刻三维距离。视线按穿格的分片常数高程计算，遮挡增加损耗而非自动断链。直连可用必须记直连；否则只能通过同一架已就位中继同时完成接入和回传，禁止中继之间多跳。一架中继不附加题面未给的并发用户数上限。','',
            '中继往返 O01，计准备、爬升/巡航/下降、建链、悬停、通信、返航、300 s 周转和组件充电。悬停位置在 DEM 内，离地高度不超过 300 m。选择方案对软任务中继增加 30 s 前后保障，后两波硬任务相应后移，并调整 Q3-024 站点。在 0、10、20、30 s 的所测取值中，10、20 s 存在额外 1 dB 链路损耗下的实际反例，30 s 通过区间充分条件。','',
            f'当前为 {m3["transport_missions"]} 个运输架次、{m3["relay_sorties"]} 个中继架次，联合完工 {m3["makespan_s"]:.3f} s；运输/中继能耗分别 {m3["transport_energy_kwh"]:.6f}/{m3["relay_energy_kwh"]:.6f} kWh，总计 {m3["transport_energy_kwh"]+m3["relay_energy_kwh"]:.6f} kWh；加权迟到 {m3["weighted_lateness_s"]:.3f} s。与快速基线相比，增加 360 s 完工时间和约 0.342408 kWh 中继能耗以换取模型内额外损耗容忍度。','',
            '通信存在性与通信表指定路径分开验证。对固定线性航迹，取每个时间区间距离的保守上界；只有全时空无遮挡充分条件通过时才去掉遮挡损耗。额外 1 dB 检查通过 38757 个初始区间及必要细分，最低经认证备选裕量 1.001449 dB。名义直连优先路径的最低经认证裕量仅约 0.0000305 dB，不能写成名义路径均有 1 dB 余量。','',
            f'通信记录共 {len(comm["records"])} 段；逐段核验直连优先和指定中继。93 个切换误差子区间每个不超过 1e-7 s，边界按原规则实时判定，补充结果为每个误差带指定全程可用的备用路径。156091 个点值及非边界连续区间复核无误；这些备用关系也被冻结给第四问。','',
            '## 5 第四问：固定关系分区与资源配置','',
            '同一运输架次所访问的服务区必须同组，求传递闭包得到 10 个绑定分量。固定第三问全部组批、访问次序、时刻、站点和通信关系后，枚举 2 组 511 个及 3 组 18660 个带标签候选。三组枚举中存在组标签置换等价候选，但不漏掉可行分区，也不影响最优评价值。跨组依赖相同中继架次时，各组复制同时间、同站点的保障任务并独立配置实体。','',
            '每类资源数量是该组占用区间的最大并发数。运输电池及中继组件占用包含充电；中继机占用包含返航后周转。因为同类资源兼容、任务均回到 O01，可按开始时刻顺序分配给最早释放的资源，区间最大并发数给出该固定任务集的最少数量。不能删除某条原通信依赖来降低资源。','',
            '用货箱运输架次的累计作业时间作为工作量，差异率定义为 (max−min)/sum；20% 为本队设定的均衡阈值。在满足阈值的分区内，依次最小化相对库存的缺口总件数、资源总件数和差异率。飞机、电池、组件按一件一单位计数仅是没有价格信息时的评价选择，不是经济成本。另给资源优先及均衡优先结果作取舍比较。','',
            '| 组数 | 各组服务区 | 需求：A/B/C机；A/B/C电池；中继/组件 | 库存缺口 | 差异率 |','| --- | --- | --- | --- | ---: |']
    for k in ('2','3'):
        sol=q4['solutions'][k]['balanced_resource_priority'];n=sol['total_required']
        zones='；'.join('G'+str(i+1)+': '+','.join(sorted(g['zones'])) for i,g in enumerate(sol['groups']))
        need=f'{n["A_craft"]}/{n["B_craft"]}/{n["C_craft"]}；{n["A_batteries"]}/{n["B_batteries"]}/{n["C_batteries"]}；{n["relay_craft"]}/{n["relay_components"]}'
        names={'A_craft':'A机','B_craft':'B机','C_craft':'C机','A_batteries':'A电池','B_batteries':'B电池','C_batteries':'C电池','relay_craft':'中继机','relay_components':'中继组件'}
        short='、'.join(f'{names[key]} {v}' for key,v in sol['shortfall'].items() if v)
        lines.append(f'| {k} | {zones} | {need} | {short} | {sol["work_imbalance_ratio"]:.2%} |')
    lines+=['','两组方案有 A 电池 1、B 电池 2 组库存余量；三组有 A、B 电池各 2 组余量。这里的库存余量是现有库存减配置需求的正部，不是能在峰值时删掉的组内资源。分区隔离使原本可跨区轮转的飞机/能源资源无法跨组复用，并导致中继任务复制，这是库存缺口增加的原因。','',
            '## 6 验证、局限和适用条件','',
            '货箱覆盖、质量、体积、逐段能量、返航 SOC、交付时刻、充电与实体冲突均由不调用求解流程的检查器重算；其中地形/通信底层仍有共用模块，因此另做几何密采样、区间界反查和故障注入。通过检查不等于真实系统试验或全部程序的形式化验证。','',
            '地形扰动是额外敏感性分析。固定端点、整幅 DEM 加高 5 m 的 8017 个采样中出现 855 次通信中断；运输机海拔降低 5 m 出现 128 次中断。因此额外 1 dB 无线损耗证书不能推出地形、定位、高度误差下的可靠性。Q4 验证继承的是名义通信，未声称分组独立后仍有全套 1 dB 备份。','',
            '能耗分式、中继飞行剖面、无并发接入上限、跨组复制和多目标优先级均已明确解释。Q2/Q3 使用有限候选与局部搜索，不保证全局最优；Q4 的穷举最优仅针对固定任务与所定义评价目标。真实应用还需地形/定位校准、风场和链路实测及作业安全审查。','',
            '## 7 图表与复现','',
            '下列图均来自当前结果，不使用模拟观察值，不作统计显著性推断；候选比较为确定性算法实验，无重复实验误差条。','']
    captions={
        '01_terrain_routes':'灰度表示原始地形高程，蓝色圆点为全部 15 个服务区，黑色星号为 O01，橙色三角为中继悬停位置。蓝线包含 Q3 全部运输航段的二维投影；往返与重复航段合并显示，不能据此判断净空或通信可行。',
        '02_safe_payload':'显示 15 个服务区、3 种机型的全部 45 个连续安全质量上界，返航余量为 20%。颜色与单元格数字均以 kg 计；这不是不可拆货箱的实际装载量。',
        '03_q2_tradeoff':'灰色圆点为本次搜索的 9 个非支配指标向量，蓝色星号为选择方案。横轴是非医疗货箱加权迟到秒数除以 3600，纵轴为能耗。非支配性按迟到、完工时间、能耗、架次数共同判断；本二维投影未显示完工时间，因此不能只看图中两轴判断其他候选是否被支配。',
        '04_q2_resources':'蓝色表示运输作业占用，灰色表示返航后的电池充电占用，时间单位为小时。覆盖 26 个架次的全部 52 条资源占用记录；只列实际用过的实体，未用的 A 电池 05、06 不列行。',
        '05_q3_resources':'蓝色表示作业占用，中继机行还包含返航后周转；灰色表示返航后充电。覆盖 26 个运输架次、15 个中继架次的全部 82 条占用记录。只列用过的实体，未用的中继能源组件 05、06 不列行。',
        '06_communication':'26 行对应全部运输架次，完整绘入 283 条名义通信记录。蓝色为直连，橙色为单跳中继；空白为该架次不处于需保障的飞行或交接阶段。微秒级状态边界无法在图中分辨，应查补充结果的边界保障记录。',
        '07_q4_resources':'灰、蓝、橙条分别表示现有库存、两组需求和三组需求；显示全部 8 类资源。采用工作量差异率不超过 20% 的资源优先分区，不代表所有评价准则下的最优分区。',
    }
    for number,(name,title) in enumerate([('01_terrain_routes','任务地形、运输航段和中继站点'),('02_safe_payload','20%余量下安全载荷'),
                       ('03_q2_tradeoff','第二问非支配候选取舍'),('04_q2_resources','第二问实体机、电池占用'),
                       ('05_q3_resources','第三问运输与中继资源占用'),('06_communication','第三问名义通信保障'),
                       ('07_q4_resources','两组、三组独立执行资源需求')],1):
        lines += [f'### {title}','',f'![{title}](figures/{name}.png)','',f'图 {number}｜{title}。{captions[name]} 源数据见同名 `.data.json`；均为确定性结果，不作统计显著性推断。','']
    lines+=['官方模板含六张表；Q3 的运输与逐箱交付、全部能源占用、通信边界规则及 Q1 安全载荷在《补充结果.json》中。完整生成命令及依赖由运行说明给出。赛队编号、最终上传命名、工具版本发布日期等须按真实记录填写，不据此改变数值模型。','',
            '## 8 资料依据','',
            '1. 本届 D 题《山区洪涝灾害下无人机运输与通信协同优化》及附录 1–3。',
            '2. 配套五份基础参数工作簿、30 m GeoTIFF 和地理空间数据说明。',
            '3. 配套结果提交模板与竞赛论文格式、AI 工具使用规定。',
            '本报告只引用已读取的原始材料与本项目计算结果。原题参考文献未逐篇核验的部分，不另作已阅读文献引用。','']
    (OUT/'解题报告.md').write_text('\n'.join(lines),encoding='utf-8')
    summary={'Q1':m1,'Q1_sortie_lower_bound':sum(lower.values()),'Q2':m2,'Q3':m3,
             'Q4':{k:q4['solutions'][k]['balanced_resource_priority'] for k in ('2','3')}}
    (OUT/'结果摘要.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('materials written','Q1 lower bound',sum(lower.values()),'Q2 selected',m2)


if __name__=='__main__':main()
