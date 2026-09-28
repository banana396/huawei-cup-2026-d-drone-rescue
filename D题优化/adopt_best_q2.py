# AI-assisted code: OpenAI Codex; metadata to be verified by team.
from audit_optimize import *
def main():
    e=Engine();q=json.loads((OUT/'q2_results.json').read_text(encoding='utf8'))
    candidates=[q['selected']]
    candidates.extend(json.loads(p.read_text(encoding='utf8')) for p in (ROOT/'checkpoints').glob('q2_cap_*.json'))
    best=min(candidates,key=e.key)
    assert not inspect(best['missions'],best['metrics'],e.nodes,e.models,e.boxes,e.res,e.terrain)
    q['selected']=best
    q['optimization']['sortie_caps']=json.loads((OUT/'q2_sortie_caps.json').read_text(encoding='utf8'))
    write(OUT/'q2_results.json',q);write(ROOT/'checkpoints'/'q2_best.json',best)
    timelines(e,best['missions'],'after');print(best['metrics'])
if __name__=='__main__':main()
