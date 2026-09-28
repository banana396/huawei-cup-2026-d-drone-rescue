# AI-assisted code: OpenAI Codex; metadata to be verified by team.
"""Run verification by default; --search reproduces the deterministic search."""
import argparse,json,shutil,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def run(*args):
    print('RUN',*args,flush=True)
    subprocess.run([sys.executable,*args],cwd=ROOT,check=True,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
def main():
    p=argparse.ArgumentParser();p.add_argument('--search',action='store_true');a=p.parse_args()
    if a.search:
        for f in (ROOT.parent/'D题求解/结果').glob('*.json'):shutil.copy2(f,ROOT/'结果'/f.name)
        for s in ('solve_q2.py','optimize_q2.py','solve_q3.py','audit_optimize.py','refine_q2.py','audit_sortie_caps.py','adopt_best_q2.py','optimize_q3_shared.py','schedule_q3_shared.py','certify_q3_intervals.py','communication_schedule.py','check_communication_schedule.py','certify_communication_boundaries.py','solve_q4.py','check_q4.py','prepare_template_data.py'):
            run(s)
        print('New matrices prepared. Export with bundled Node: export_optimized.mjs, then run this verifier again.')
    run('check_q2.py');run('verify_optimized.py')
    if not a.search:run('check_template.py');run('build_optimization_report.py')
    run('archive_reference_results.py')
if __name__=='__main__':main()
