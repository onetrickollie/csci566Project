"""Offline diagnostic for supervisor review N1–N6. Prints observations; makes no API calls.
Run: .venv/bin/python docs/review/llm_regressions.py
These are deliberately adversarial cases, not assertions that bugs are desired behavior.
"""
import sys,json,tempfile,random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from taskflow.llm import client as cm
from taskflow.llm.client import LLMClient,LLMError
from taskflow.agents import tracker,llm_planners
from taskflow.env.state import Constraints,ConstraintDiff,SLOTS
from taskflow.common import query_index,TASKS_DIR
from taskflow.env.tools import Cache
from taskflow.agents.planners import compose_global,replan_local
from taskflow.env.verifier import verify,plan_cost
from taskflow.env.episode import TurnEnv,run_episode
from taskflow.coordinators.llm_coordinator import state_summary,LLMCoordinator
from taskflow.learning.encode import encode
from taskflow.data.tasks import load
out={}
class Stub(LLMClient):
 def _call(self,s,u,m):return self.base_url,10,5
cm.CACHE_DIR=Path(tempfile.mkdtemp(prefix='taskflow-cache-review-'))
a=Stub('openai','same-model',base_url='https://server-a.invalid/v1');b=Stub('openai','same-model',base_url='https://server-b.invalid/v1')
out['endpoint_cache_collision']={'a':a.complete('system','user'),'b':b.complete('system','user'),'b_usage':vars(b.usage)}
c=Constraints(1000,house_rules=['pets'])
d=tracker.validate(ConstraintDiff('replace','house_rule','pets','visitors'),c)
out['house_replace']={'before':c.house_rules,'after':d.apply(c).house_rules}
class NoUpdate:
 def complete_json(self,*args,**kwargs):return {'op':'none'}
d,source=tracker.parse_any('Is Italian food available?',Constraints(1000,cuisines=['Chinese']),NoUpdate())
out['no_update_overridden']={'source':source,'diff':d.to_dict()}
for msg in ['What room type do we have?', 'Choose restaurants rated highly.']:
 try:tracker.parse_any(msg,c,None);result='no error'
 except Exception as e:result=type(e).__name__+': '+str(e)
 out['parse_'+msg]=result
q=next(iter(query_index().values()));c=Constraints(5000);cache=Cache();p=compose_global(q,c,cache);env=TurnEnv(q,c,p,cache,'Let\'s change the budget to $4,000.',random.Random(0));summary=state_summary(env);encoded=encode(env).copy();env.cache.data['accommodation']=[]
out['observation_mismatch']={'summary_unchanged':summary==state_summary(env),'features_changed':int((encoded!=encode(env)).sum())}
class Expensive:
 def complete_json(self,s,u,max_tokens=300):
  inp=json.loads(u.split('INPUT:\n')[1]);out['meals_prompt_budget']=inp['budget_left'];return {'restaurants':[r['name'] for r in sorted(inp['candidates'],key=lambda r:r['cost_per_person'],reverse=True)[:6]]}
c=Constraints(5000);cache=Cache();p=compose_global(q,c,cache);c.budget=verify(q,c,p).total_cost+1
np=replan_local(q,c,p,'meals',cache,Expensive());out['meals_budget']={'budget':c.budget,'old_cost':verify(q,c,p).total_cost,'new_cost':verify(q,c,np).total_cost,'new_valid':verify(q,c,np).passed}
class Broken(LLMClient):
 def _call(self,*args):raise LLMError('HTTP 401 unauthorized (synthetic)')
broken=Broken('openai','unavailable',use_cache=False);ep=load(TASKS_DIR,'test')[0];q=query_index()[ep.qid];pol=LLMCoordinator(broken)
r=run_episode(ep,q,pol,llm=broken);out['all_api_calls_fail']={'usage':vars(broken.usage),'final_pass':r.final_pass,'tracker_ok':[t.tracker_ok for t in r.turns],'measured_requests':[t.measured_llm_calls for t in r.turns],'fallbacks':pol.fallbacks}
# Same prompt cache cannot validate whether provider was actually called.
print(json.dumps(out,indent=2))
