# AI-assisted code: OpenAI Codex; metadata to be verified by team.
"""Keep only current evidence in 结果; preserve copied historical JSON separately."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parent
KEEP={'q1_results_v2.json','q2_results.json','q2_check.json','q2_sortie_caps.json','q3_solution.json','q3_check.json',
      'q3_spatial_search.json','q3_shared_search_check.json','q3_interval_certificate.json','q3_margin_certificate_1db.json',
      'q3_communication_schedule.json','q3_communication_check.json','q3_boundary_guards.json','q4_results.json','q4_check.json',
      'template_data.json','template_check.json','optimized_validation.json','workbook_preservation_check.json','delivery_manifest.json'}
def main():
    dest=(ROOT/'历史参考结果').resolve();source=(ROOT/'结果').resolve()
    assert dest.parent==ROOT.resolve() and source.parent==ROOT.resolve()
    dest.mkdir(exist_ok=True)
    count=0
    for p in source.glob('*.json'):
        if p.name not in KEEP:
            target=dest/p.name
            assert p.resolve().parent==source and target.resolve().parent==dest
            if target.exists():
                assert target.read_bytes()==p.read_bytes(),f'Archive collision: {p.name}'
                # Preserve both files when already archived; no deletion needed.
                continue
            shutil.move(str(p),str(target));count+=1
    print('historical JSON archived',count)
if __name__=='__main__':main()
