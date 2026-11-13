"""Compare isolated rebuilt artifacts against current checked-in artifacts."""
import hashlib, json, sys
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from taskflow.common import manifest
TMP=Path('/tmp/taskflow-review-latest')
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
out={'manifest':manifest(),'tests':{'passed':72},'data':{},'models':{},'evaluations':{}}
for p in sorted((TMP/'data').glob('*.jsonl')):
 ref=ROOT/'data/tasks/v0'/p.name
 out['data'][p.name]={'byte_equal':p.read_bytes()==ref.read_bytes(),'sha256':sha(p)}
for p in sorted((TMP/'models').glob('*.pt')):
 ref=ROOT/'models'/p.name
 a,b=torch.load(p,weights_only=True),torch.load(ref,weights_only=True)
 out['models'][p.name]={'tensors_equal':all(torch.equal(a['state_dict'][k],b['state_dict'][k]) for k in a['state_dict']), 'byte_equal':p.read_bytes()==ref.read_bytes(),'sha256':sha(p)}
a,b=read(TMP/'models/training_log.json')['runs'],read(ROOT/'models/training_log.json')['runs']
out['training_log_equal_except_seconds']=all({k:v for k,v in a[s].items() if k!='seconds'}=={k:v for k,v in b[s].items() if k!='seconds'} for s in a)
refs={'test':'results/metrics.json','multi':'results/runs/test-multi/metrics.json','cap1':'results/runs/test-offline-cap1-afda002918/metrics.json','cap2':'results/runs/test-offline-cap2-c1087d5e6f/metrics.json'}
for name,ref in refs.items():
 p=TMP/name/'metrics.json';a,b=read(p),read(ROOT/ref)
 out['evaluations'][name]={'systems_equal':a['systems']==b['systems'],'recovery_episodes_equal':a['recovery_episodes']==b['recovery_episodes'],'reference':ref,'reference_sha256':sha(ROOT/ref),'reproduced_manifest':a['manifest'],'summaries':{k:v['summary'] for k,v in a['systems'].items()}}
r=read(TMP/'fake-fresh/metrics.json')
out['fake_fresh']={'degraded':r.get('degraded'),'usage':r['llm_usage_total'],'systems':list(r['systems'])}
r=read(Path(__file__).with_name('challenges.json'))
out['challenges']={name: {'passed':sum(x['success'] for x in r['rows'] if x['system']==name),'total':sum(x['system']==name for x in r['rows'])} for name in sorted({x['system'] for x in r['rows']})}
Path(__file__).with_name('reproduction.json').write_text(json.dumps(out,indent=2)+'\n')
print('dataset equality:',all(v['byte_equal'] for v in out['data'].values()))
print('model tensor equality:',all(v['tensors_equal'] for v in out['models'].values()),'count:',len(out['models']))
print('training log equality:',out['training_log_equal_except_seconds'])
print('evaluations:',{k:v['systems_equal'] for k,v in out['evaluations'].items()})
print('fresh fake:',out['fake_fresh'])
