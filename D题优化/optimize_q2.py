# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""在多点组批基线上联合改进顺序、实体机与电池选择，保存多目标对照。

问题三的初始组批仍显式取 merged 基线；问题二结果使用 selected。
不把有限邻域搜索声称为全局最优。
"""
import json
from math import inf

from d_common import Terrain,load_inputs,load_resources,make_leg
from solve_q2 import OUT,Task,hard_deadline,schedule
from check_q2 import inspect


def metrics(rows,boxes):
    delivery={i:t for r in rows for i,t in r['delivery_s'].items()}
    return {'sorties':len(rows),'energy_kwh':sum(r['energy_kwh'] for r in rows),
            'makespan_s':max(r['return_s'] for r in rows),
            'weighted_lateness_s':sum(boxes[i].priority*max(0,t-boxes[i].expected_s)
                                      for i,t in delivery.items() if boxes[i].kind!='医疗物资'),
            'medical_late':sum(t>boxes[i].expected_s+1e-8 for i,t in delivery.items() if boxes[i].kind=='医疗物资'),
            'first_late':sum(t>boxes[i].first_deadline_s+1e-8 for i,t in delivery.items() if boxes[i].first)}


def main():
    source=json.loads((OUT/'q2_results.json').read_text(encoding='utf-8'))
    nodes,models,boxes=load_inputs();res=load_resources();terrain=Terrain()
    legs={(a,b):make_leg(terrain,nodes[a],nodes[b]) for a in nodes for b in nodes if a!=b}
    tasks=[Task(tuple((s['zone'],tuple(s['boxes'])) for s in m['stops'])) for m in source['merged']['missions']]
    hard=[t for t in tasks if any(hard_deadline(boxes[i])<inf for i in t.boxes)]
    soft=[t for t in tasks if t not in hard]
    hard.sort(key=lambda t:(min(hard_deadline(boxes[i]) for i in t.boxes),
                           -max(legs['O01',z].distance_m for z,_ in t.stops),-len(t.boxes)))
    profiles={};seen=set();candidates=[];infeasible=0
    def key(item):
        m=item['metrics'];return (m['weighted_lateness_s'],m['makespan_s'],m['energy_kwh'],m['sorties'])
    def evaluate(order,selection,label):
        nonlocal infeasible
        signature=(tuple(order),selection)
        if signature in seen:return None
        seen.add(signature)
        try:rows=schedule(tasks,nodes,models,boxes,res,legs,hard+list(order),selection,profiles)
        except RuntimeError:infeasible+=1;return None
        item={'label':label,'selection':selection,'metrics':metrics(rows,boxes),'missions':rows,'order':list(order)}
        candidates.append(item);return item
    sorts={
        'due':lambda t:min(boxes[i].expected_s for i in t.boxes),
        'weight':lambda t:-sum(boxes[i].priority for i in t.boxes),
        'due_weight':lambda t:min(boxes[i].expected_s for i in t.boxes)/sum(boxes[i].priority for i in t.boxes),
        'far':lambda t:-max(legs['O01',z].distance_m for z,_ in t.stops),
        'near':lambda t:max(legs['O01',z].distance_m for z,_ in t.stops),
    }
    for label,ordering in sorts.items():
        for selection in ('delivery','lateness','energy'):
            evaluate(sorted(soft,key=ordering),selection,label)
    # 不同分配准则分别做严格改进的交换邻域，避免只搜索一个起点。
    rounds={}
    for selection in ('delivery','lateness','energy'):
        incumbent=min((x for x in candidates if x['selection']==selection),key=key)
        for iteration in range(8):
            best=incumbent;order=incumbent['order']
            for i in range(len(order)):
                for j in range(i+1,len(order)):
                    trial=list(order);trial[i],trial[j]=trial[j],trial[i]
                    item=evaluate(trial,selection,f'{selection}_swap_{iteration+1}')
                    if item is not None and key(item)<key(best):best=item
            rounds[selection]=iteration+1
            if best is incumbent:break
            incumbent=best
        print(selection,'rounds',rounds[selection],'best',incumbent['metrics'],flush=True)
    reference={'label':'merged_baseline','selection':'delivery','metrics':source['merged']['metrics'],
               'missions':source['merged']['missions']}
    pool=[reference]+candidates
    best=min(pool,key=key)
    cols=('weighted_lateness_s','makespan_s','energy_kwh','sorties')
    def dominates(a,b):
        return all(a['metrics'][c]<=b['metrics'][c]+1e-8 for c in cols) and any(a['metrics'][c]<b['metrics'][c]-1e-8 for c in cols)
    front=[x for x in pool if not any(dominates(y,x) for y in pool)]
    unique={tuple(round(x['metrics'][c],6) for c in cols):x for x in front}
    checks=[]
    for x in [best]+list(unique.values()):
        errors=inspect(x['missions'],x['metrics'],nodes,models,boxes,res,terrain)
        checks.append({'label':x['label'],'issues':errors})
        if errors:raise RuntimeError(checks[-1])
    source['selected']={k:v for k,v in best.items() if k!='order'}
    source['optimization']={'objective_priority':list(cols),'unique_candidates':len(seen),'infeasible_candidates':infeasible,
                            'rounds':rounds,'scope':'固定多点组批，5种排序、3种实体/电池分配准则及交换邻域；非全局最优证明',
                            'pareto_candidates':[{k:v for k,v in x.items() if k!='order'} for x in unique.values()],
                            'independent_checks':checks,
                            'q3_inheritance':'Q3仍从merged原始多点组批基线构建自己的通信约束调度，不直接继承selected时间表'}
    (OUT/'q2_results.json').write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf-8')
    print('selected',best['label'],best['metrics'],'candidates',len(seen),'pareto',len(unique))


if __name__=='__main__':main()
