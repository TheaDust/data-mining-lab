"""最终交付验收：读取文件、比对历史及离线复跑，不调用模型。"""
from pathlib import Path
import csv
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.audit_deps'))
from openpyxl import load_workbook
from PIL import Image

def load(p): return json.loads(p.read_text(encoding='utf8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'results'; aud=ROOT/'audit_resolution'; snap=ROOT/'history/pre_independent_audit'
    final=load(out/'final_mapping.json'); summary=load(out/'summary.json')
    assert len(final)==summary['final_pairs']==41
    assert sum(summary['categories'].values())==len(final)
    for p in out.glob('*.json'): load(p)
    for p in aud.glob('*.json'): load(p)
    for rel,expected in load(snap/'snapshot_manifest.json').items(): assert sha(snap/rel)==expected,rel
    provenance=load(aud/'provenance_checks.json')
    for rel,expected in provenance['review_package_manifest'].items(): assert sha(ROOT/'review_package'/rel)==expected,rel
    for name in ('raw_pairs.json','validated_pairs.json','rejected_pairs.json','run_log.json','dedup_log.json','negative_audit.json'):
        assert sha(out/name)==sha(snap/'results'/name)
    workbook=load_workbook(out/'final_mapping.xlsx',read_only=True,data_only=False)
    table=list(workbook['条件建议映射'].values)
    assert len(table)==len(final)+1
    for excel,record in zip(table[1:],final):
        for key,value in zip(table[0],excel):
            target=record[key]
            if isinstance(target,(list,dict)): assert json.loads(value)==target
            else: assert value==target
    manual=list(workbook['人工审核'].values)
    assert len(manual)==len(final)+1
    for row in manual[1:]:
        values=dict(zip(manual[0],row))
        assert not values.get('human_label') and not values.get('reviewer')
    with (out/'category_counts.csv').open(encoding='utf-8-sig',newline='') as f:
        assert {r['条件类型']:int(r['关系数量']) for r in csv.DictReader(f)}==summary['categories']
    with (out/'scenic_category_counts.csv').open(encoding='utf-8-sig',newline='') as f:
        records=list(csv.DictReader(f)); assert sum(int(r[c]) for r in records for c in summary['categories'])==len(final)
    for name in ('condition_types.png','scenic_comparison.png'):
        im=Image.open(out/name); im.verify()
    for r in load(aud/'resolution_log.json'):
        assert set(r['final_pair_ids'])<={x['pair_id'] for x in final}
    report=(ROOT/'REPORT.md').read_text(encoding='utf8')
    assert all(f'## 5.{i}' in report for i in range(1,6))
    assert '真实人工核验完成数仍为0' in report
    assert '32−3+7+5=41' in report
    # 实际从默认入口重放，再比对核心结果和逐项落实记录字节哈希，检验幂等性。
    core=[out/'final_mapping.json',out/'summary.json',out/'review_dedup_log.json',aud/'resolution_log.json']
    before={str(p):sha(p) for p in core}
    subprocess.run([sys.executable,str(ROOT/'run.py')],check=True,capture_output=True)
    after={str(p):sha(p) for p in core}
    assert before==after
    checks={'status':'passed','final_pairs':len(final),'resolution_items':108,'json_valid':True,
      'excel_json_cells_equal':True,'category_csv_equal':True,'scenic_counts_equal':True,'png_valid':True,
      'original_outputs_preserved':True,'snapshot_and_review_package_unchanged':True,'report_sections_consistent':True,
      'actual_default_entry_replay_idempotent':True,'core_sha256':after,'new_model_calls':0,
      'human_gold':False,'human_review':'待真实人工确认'}
    (out/'final_acceptance.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf8')
    print('final acceptance passed; 41 pairs; offline replay identical')

if __name__=='__main__': main()
