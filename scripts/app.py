"""Interactive web demo: plan any trip, then revise it in plain language.

    python scripts/app.py              # http://localhost:8566 (opens your browser)
    python scripts/app.py --port 9000 --no-open
    python scripts/app.py --llm openai # free-form messages via the configured LLM

1. Type a start city and a destination (any of the ~250 TravelPlanner cities;
   typos get suggestions), a start date in March 2022, travelers, budget and
   optional requirements. The planners build a 3-day itinerary.
2. Type revisions ("Let's change the budget to $1,200.", "The place needs to
   allow pets.", ...). Every coordinator handles the same message on its own
   copy of the trip, shown side by side: actions, changed slots, validity,
   cost.

Offline, the rule-based tracker understands the phrasings shown as
suggestions; with an LLM backend it understands free-form messages. Runs on
localhost only; no data leaves the machine unless an LLM backend is set.
"""

import argparse
import json
import random
import sys
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taskflow.agents.planners import compose_global, min_cost  # noqa: E402
from taskflow.common import baseline_policies, learned_policy  # noqa: E402
from taskflow.data.world import build_world  # noqa: E402
from taskflow.env.episode import TurnEnv  # noqa: E402
from taskflow.env.state import CUISINES, HOUSE_RULES, ROOM_TYPES, TRANSPORT_RULES, Constraints  # noqa: E402
from taskflow.env.tools import Cache  # noqa: E402
from taskflow.env.verifier import verify  # noqa: E402

ORDER = [("transport_out", "Day 1 · transport"), ("d1_attraction", "Day 1 · attraction"),
         ("d1_dinner", "Day 1 · dinner"), ("accommodation", "Nights 1–2 · stay"),
         ("d2_breakfast", "Day 2 · breakfast"), ("d2_attraction_1", "Day 2 · attraction"),
         ("d2_lunch", "Day 2 · lunch"), ("d2_attraction_2", "Day 2 · attraction"),
         ("d2_dinner", "Day 2 · dinner"), ("d3_breakfast", "Day 3 · breakfast"),
         ("d3_attraction", "Day 3 · attraction"), ("d3_lunch", "Day 3 · lunch"),
         ("transport_back", "Day 3 · transport")]
SUGGESTIONS = ["Let's change the budget to $1,200.", "Could we also try some Mexican food?",
               "The place needs to allow pets.", "Please, no flight on this trip.",
               "Now quality matters more to me than anything else.",
               "Only restaurants rated at least 4.0 please.", "Book us a private room for the stay.",
               "Now cost matters more to me than anything else."]

WORLD = None
LLM = None
SESSIONS: dict = {}
LOCK = threading.Lock()


def systems():
    base = baseline_policies(LLM)
    out = [("always_global", "Always regenerate", base["always_global"]),
           ("static_rules", "Static rules", base["static_rules"]),
           ("learned", "Learned coordinator", learned_policy("bc_aug_dagger3", 0))]
    if LLM is not None:
        out.append(("llm_coordinator", "LLM coordinator", base["llm_coordinator"]))
    else:
        out.append(("oracle", "Scripted expert", base["oracle"]))
    return out


def describe(c: Constraints) -> str:
    parts = [f"budget ${c.budget:,.0f}", f"{c.people} traveler(s)"]
    if c.room_type:
        parts.append(c.room_type)
    parts += [f"must allow {h}" for h in c.house_rules]
    if c.cuisines:
        parts.append("cuisines: " + ", ".join(c.cuisines))
    if c.transport:
        parts.append(c.transport)
    if c.min_rating is not None:
        parts.append(f"restaurants ≥ {c.min_rating:g}")
    if c.priority:
        parts.append(f"priority: {c.priority}")
    return "; ".join(parts)


def transport_label(q, key: str) -> str:
    if key.startswith("flight:"):
        num = key.split(":", 1)[1]
        for fl in q.db.flights.values():
            for f in fl:
                if f.number == num:
                    return f"Flight {num}, {f.origin} → {f.dest}, {f.dep}–{f.arr}, ${f.price:,.0f}/person"
        return key
    for (mode, o, d), g in q.db.ground.items():
        if mode == key:
            est = " (estimated from distance)" if g.estimated else ""
            return f"{mode.capitalize()}, ~{g.distance_km:,.0f} km, {g.duration}, ${g.cost:,.0f}{est}"
    return key


def plan_rows(q, plan, prev=None):
    rows = []
    for slot, label in ORDER:
        v = plan.get(slot, "-")
        shown = transport_label(q, v) if slot.startswith("transport") else str(v).replace("\n", " / ")
        rows.append({"label": label, "value": shown,
                     "changed": prev is not None and prev.get(slot) != plan.get(slot)})
    return rows


def plan_view(q, c, plan, prev=None):
    rep = verify(q, c, plan)
    return {"rows": plan_rows(q, plan, prev), "valid": rep.passed, "cost": round(rep.total_cost),
            "breakdown": {k: round(v) for k, v in rep.component_cost.items()},
            "violations": sorted(rep.kinds())}


# ---------------------------------------------------------------------------
def api_cities(_):
    return {"start": WORLD.start_cities, "destinations": WORLD.destinations,
            "room_types": ROOM_TYPES, "house_rules": HOUSE_RULES, "cuisines": CUISINES,
            "transport_rules": TRANSPORT_RULES, "suggestions": SUGGESTIONS,
            "llm": LLM.label if LLM else None}


def api_route(body):
    org, _ = WORLD.resolve(body.get("org", ""), WORLD.start_cities)
    dest, _ = WORLD.resolve(body.get("dest", ""), WORLD.destinations)
    if not org or not dest or org == dest:
        return {"flight_dates": []}
    return {"flight_dates": WORLD.flight_dates(org, dest)}


def api_trip(body):
    org, s1 = WORLD.resolve(body.get("org", ""), WORLD.start_cities)
    dest, s2 = WORLD.resolve(body.get("dest", ""), WORLD.destinations)
    if not org:
        return {"error": f"Unknown start city “{body.get('org', '')}”.", "suggest_org": s1}
    if not dest:
        return {"error": f"No hotel/restaurant data for “{body.get('dest', '')}”.", "suggest_dest": s2}
    if org == dest:
        return {"error": "Start and destination must differ."}
    start = body.get("date") or "2022-03-10"
    if not ("2022-03-01" <= start <= "2022-03-29"):
        return {"error": "The data covers March 2022: pick a start date between Mar 1 and Mar 29."}
    try:
        people = max(1, min(8, int(body.get("people", 1))))
        budget = float(body.get("budget", 0))
    except (TypeError, ValueError):
        return {"error": "Travelers and budget must be numbers."}
    c = Constraints(budget=budget, people=people,
                    room_type=body.get("room_type") or None,
                    house_rules=[h for h in body.get("house_rules", []) if h in HOUSE_RULES],
                    cuisines=[x for x in body.get("cuisines", []) if x in CUISINES],
                    transport=body.get("transport") or None)
    q = WORLD.trip_query(org, dest, start, people, budget)
    if not q.db.flights and not q.db.ground:
        return {"error": f"No transport data between {org} and {dest}."}
    cache = Cache()
    plan = compose_global(q, c, cache)
    rep = verify(q, c, plan)
    if not rep.passed:
        cheapest = min_cost(q, c)
        hint = (f"The cheapest plan that meets the other requirements costs about ${cheapest:,.0f}."
                if cheapest < 1e8 else "No combination in the data meets these requirements.")
        return {"error": f"Can't build a valid plan: {', '.join(sorted(rep.kinds()))}. {hint}"}
    sid = uuid.uuid4().hex[:12]
    state = {}
    for key, label, pol in systems():
        state[key] = {"label": label, "policy": pol, "c": c.copy(), "plan": dict(plan), "cache": cache.copy(),
                      "rng": random.Random(0), "ok": 0, "turns": 0, "llm_calls": 0, "changed": 0}
    SESSIONS[sid] = {"q": q, "state": state}
    notes = []
    if not q.db.flights:
        dates = WORLD.flight_dates(org, dest)
        notes.append("No flights in the data for these dates" +
                     (f" (flights exist for start dates {', '.join(d[5:] for d in dates[:6])})" if dates else "") +
                     "; showing driving/taxi.")
    if any(g.estimated for g in q.db.ground.values()):
        notes.append("Driving and taxi options are estimated from the distance between the cities.")
    return {"session": sid, "title": f"{org} → {dest}", "dates": q.dates, "request": describe(c),
            "plan": plan_view(q, c, plan), "notes": notes}


def api_update(body):
    sess = SESSIONS.get(body.get("session"))
    if not sess:
        return {"error": "Session expired; plan the trip again."}
    msg = (body.get("message") or "").strip()
    if not msg:
        return {"error": "Type a change to the trip."}
    q = sess["q"]
    results, parsed = [], None
    for key, st in sess["state"].items():
        env = TurnEnv(q, st["c"], st["plan"], st["cache"], msg, st["rng"], LLM,
                      sample_global=getattr(st["policy"], "sample_global", True))
        if parsed is None:
            d = env.diff
            parsed = {"source": env.tracker_source,
                      "text": None if d is None else f"{d.op} {d.target_type}: {d.old} → {d.new}"}
            if d is None:
                hint = ("That message doesn't change any requirement." if env.tracker_source == "llm-none" else
                        "Couldn't read that as a change" + ("" if LLM else
                        " (offline mode understands the suggested phrasings; set an LLM backend for free-form text)") + ".")
                return {"parsed": parsed, "error": hint}
        while not env.done:
            env.step(st["policy"].act(env))
        asked = env.terminal == "ASK_CLARIFICATION"
        if asked:
            new_c, new_plan = env.before, env.start_plan
        else:
            new_c, new_plan = env.c, env.plan
        view = plan_view(q, env.c if not asked else env.before, new_plan, env.start_plan)
        changed = sum(r["changed"] for r in view["rows"])
        st.update(c=new_c, plan=new_plan)
        st["turns"] += 1
        st["llm_calls"] += env.llm_calls
        st["changed"] += changed
        st["ok"] += int(asked or view["valid"])
        results.append({"key": key, "label": st["label"], "actions": env.history, "terminal": env.terminal,
                        "asked": asked, "changed": changed, "llm_calls": env.llm_calls,
                        "tool_calls": env.tool_calls, "plan": view,
                        "request": describe(new_c),
                        "totals": {k: st[k] for k in ("turns", "ok", "llm_calls", "changed")}})
    return {"parsed": parsed, "results": results}


ROUTES = {"/api/cities": api_cities, "/api/route": api_route, "/api/trip": api_trip, "/api/update": api_update}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if self.path == "/api/cities":
            return self._send(200, api_cities(None))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        fn = ROUTES.get(self.path)
        if fn is None:
            return self._send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            with LOCK:
                out = fn(body)
            self._send(200, out)
        except Exception as e:  # keep the demo alive; report the problem in the UI
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>TaskFlow-Travel</title>
<style>
:root{--bg:#fafaf9;--fg:#1c1917;--muted:#78716c;--card:#fff;--line:#e7e5e4;--hl:#fef3c7;--hlfg:#92400e;
--ok:#15803d;--bad:#b91c1c;--chip:#f5f5f4;--accent:#1d4ed8;--accentfg:#fff;--input:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#f5f5f4;--muted:#a8a29e;--card:#292524;--line:#44403c;
--hl:#422006;--hlfg:#fcd34d;--ok:#4ade80;--bad:#f87171;--chip:#3f3a36;--accent:#93c5fd;--accentfg:#1c1917;--input:#1c1917}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,sans-serif}
main{max-width:1400px;margin:0 auto;padding:20px 16px 80px}h1{font-size:22px;margin:0}h2{font-size:16px;margin:0 0 8px}
.sub{color:var(--muted);margin:2px 0 16px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;min-width:0}
form .row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:10px}label{display:flex;flex-direction:column;gap:3px;font-size:12px;color:var(--muted);flex:1 1 150px}
input,select,button{font:inherit;color:var(--fg);background:var(--input);border:1px solid var(--line);border-radius:7px;padding:7px 9px}
button{background:var(--accent);color:var(--accentfg);border-color:var(--accent);cursor:pointer;font-weight:600}
button.ghost{background:transparent;color:var(--fg);border-color:var(--line);font-weight:400}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{background:var(--chip);border:0;color:var(--fg);border-radius:99px;padding:4px 10px;font-size:12px;font-weight:400}
.cuis{display:flex;flex-wrap:wrap;gap:8px;font-size:12px}.cuis label{flex:0 0 auto;flex-direction:row;align-items:center;color:var(--fg)}
.err{color:var(--bad);margin:8px 0}.note{color:var(--muted);font-size:12px;margin:4px 0}.hint{font-size:12px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:12px}
.card h3{font-size:14px;margin:0 0 6px;display:flex;justify-content:space-between;gap:8px}
.badge{font-size:11px;padding:1px 8px;border-radius:99px;font-weight:600;white-space:nowrap;border:1px solid}
.ok{color:var(--ok)}.bad{color:var(--bad)}.acts{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0 8px}
.act{background:var(--chip);border-radius:6px;padding:1px 6px;font:11px ui-monospace,monospace}.stats{color:var(--muted);font-size:12px;margin-bottom:6px}
table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}td{padding:2px 4px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
td.k{color:var(--muted);width:38%}tr.ch td{background:var(--hl);color:var(--hlfg)}
.turn{margin-top:22px;padding-top:14px;border-top:1px solid var(--line)}.msg{font-size:15px}.parsed{color:var(--muted);font-size:12px}
.chat{display:flex;gap:8px;margin:12px 0 6px}.chat input{flex:1}.hidden{display:none}.initial{max-width:560px;margin-top:12px}
.totals{font-size:12px;color:var(--muted);margin-top:6px}
</style></head><body><main>
<h1>TaskFlow-Travel</h1><div class=sub>Plan a 3-day trip, then change your mind. Each coordinator handles your change on its own copy of the trip.</div>
<section class=card id=setup><h2>1 · Your trip</h2>
<form id=tripform><div class=row>
<label>From<input id=org list=orgs placeholder="e.g. Chicago" required></label>
<label>To<input id=dest list=dests placeholder="e.g. Seattle" required></label>
<label>Start date (March 2022)<input id=date type=date min=2022-03-01 max=2022-03-29 value=2022-03-10></label>
<label>Travelers<input id=people type=number min=1 max=8 value=2></label>
<label>Total budget ($)<input id=budget type=number min=100 step=50 value=3000></label></div>
<div class=row><label>Room type<select id=room><option value="">any</option></select></label>
<label>Must allow<select id=rule><option value="">nothing specific</option></select></label>
<label>Transport<select id=trans><option value="">any</option></select></label></div>
<div class=hint>Cuisines to include</div><div class=cuis id=cuis></div>
<div class=row style="margin-top:12px"><button type=submit>Plan trip</button><span class=hint id=routehint></span></div>
<div class=err id=triperr></div></form>
<datalist id=orgs></datalist><datalist id=dests></datalist></section>
<section id=tripview class=hidden>
<div class="card initial"><h3><span id=title></span><span class="badge ok" id=initbadge></span></h3>
<div class=stats id=reqline></div><div id=notes></div><div id=initplan></div></div>
<section class=card style="margin-top:14px"><h2>2 · Change something</h2>
<form id=chatform class=chat><input id=msg placeholder="e.g. Let's change the budget to $1,200." autocomplete=off><button>Send</button>
<button type=button class=ghost id=newtrip>New trip</button></form>
<div class=chips id=sugg></div><div class=err id=chaterr></div><div class=note id=llmnote></div></section>
<div id=turns></div></section>
</main><script>
const $=s=>document.querySelector(s);let SID=null,TURN=0;
const el=(t,a={},...kids)=>{const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k=='class')e.className=v;else e.setAttribute(k,v)}
for(const k of kids)e.append(k instanceof Node?k:document.createTextNode(k??''));return e};
async function post(p,b){const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.json()}
function table(rows){const t=el('table');for(const r of rows)t.append(el('tr',r.changed?{class:'ch'}:{},el('td',{class:'k'},r.label),el('td',{},r.value)));return t}
function badge(ok,text){return el('span',{class:'badge '+(ok?'ok':'bad')},text)}
async function init(){const c=await (await fetch('/api/cities')).json();
for(const x of c.start)$('#orgs').append(el('option',{value:x}));for(const x of c.destinations)$('#dests').append(el('option',{value:x}));
for(const x of c.room_types)$('#room').append(el('option',{value:x},x));for(const x of c.house_rules)$('#rule').append(el('option',{value:x},x));
for(const x of c.transport_rules)$('#trans').append(el('option',{value:x},x));
for(const x of c.cuisines)$('#cuis').append(el('label',{},el('input',{type:'checkbox',value:x}),' '+x));
for(const s of c.suggestions){const b=el('button',{type:'button',class:'chip'},s);b.onclick=()=>{$('#msg').value=s;$('#msg').focus()};$('#sugg').append(b)}
$('#llmnote').textContent=c.llm?('LLM tracker on ('+c.llm+'): free-form messages work.'):'Offline mode: the tracker understands phrasings like the suggestions above. Configure an LLM in .env for free-form messages.'}
async function routeHint(){const o=$('#org').value,d=$('#dest').value;if(!o||!d){$('#routehint').textContent='';return}
const r=await post('/api/route',{org:o,dest:d});$('#routehint').textContent=r.flight_dates.length?('Flights in the data for start dates: '+r.flight_dates.map(x=>x.slice(5)).join(', ')):'No flights in the data for this route; driving/taxi will be used.'}
$('#org').onchange=routeHint;$('#dest').onchange=routeHint;
$('#tripform').onsubmit=async e=>{e.preventDefault();$('#triperr').textContent='Planning…';
const body={org:$('#org').value,dest:$('#dest').value,date:$('#date').value,people:$('#people').value,budget:$('#budget').value,
room_type:$('#room').value,house_rules:$('#rule').value?[$('#rule').value]:[],transport:$('#trans').value,
cuisines:[...document.querySelectorAll('#cuis input:checked')].map(x=>x.value)};
const r=await post('/api/trip',body);if(r.error){let m=r.error;const s=r.suggest_org||r.suggest_dest;if(s&&s.length)m+=' Did you mean: '+s.join(', ')+'?';$('#triperr').textContent=m;return}
$('#triperr').textContent='';SID=r.session;TURN=0;$('#turns').innerHTML='';$('#title').textContent=r.title+'  ·  '+r.dates[0]+' to '+r.dates[2];
$('#initbadge').textContent='valid · $'+r.plan.cost.toLocaleString();$('#reqline').textContent='Request: '+r.request;
$('#notes').innerHTML='';for(const n of r.notes)$('#notes').append(el('div',{class:'note'},n));
$('#initplan').innerHTML='';$('#initplan').append(table(r.plan.rows));$('#setup').classList.add('hidden');$('#tripview').classList.remove('hidden');$('#msg').focus()};
$('#newtrip').onclick=()=>{$('#tripview').classList.add('hidden');$('#setup').classList.remove('hidden')};
$('#chatform').onsubmit=async e=>{e.preventDefault();const m=$('#msg').value;$('#chaterr').textContent='Thinking…';
const r=await post('/api/update',{session:SID,message:m});if(r.error){$('#chaterr').textContent=r.error;return}
$('#chaterr').textContent='';$('#msg').value='';TURN++;
const sec=el('section',{class:'turn'},el('h2',{},'Change '+TURN),el('div',{class:'msg'},'“'+m+'”'),
el('div',{class:'parsed'},'Understood as: '+r.parsed.text+' ('+r.parsed.source+')'));const g=el('div',{class:'grid'});
for(const s of r.results){const p=s.plan;let b;
if(s.asked)b=badge(true,'asked you to reconsider');else if(p.valid)b=badge(true,'valid · $'+p.cost.toLocaleString());else b=badge(false,p.violations.join(', ')||'failed');
const acts=el('div',{class:'acts'});for(const a of s.actions)acts.append(el('span',{class:'act'},a));
const card=el('div',{class:'card'},el('h3',{},s.label,b),acts,el('div',{class:'stats'},s.changed+'/13 slots changed · '+s.llm_calls+' LLM calls · '+s.tool_calls+' searches'));
if(s.asked)card.append(el('div',{class:'note'},'"That change can\'t be met together with your other requirements, so I kept the previous plan."'));
card.append(table(p.rows),el('div',{class:'totals'},'So far: '+s.totals.ok+'/'+s.totals.turns+' changes handled · '+s.totals.llm_calls+' LLM calls · '+s.totals.changed+' slots changed'));g.append(card)}
sec.append(g);$('#turns').prepend(sec)};
init();
</script></body></html>"""


def main():
    global WORLD, LLM
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8566)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--llm", default=None, help="offline | fake | openai | anthropic")
    a = ap.parse_args()
    from taskflow.llm.client import get_client

    LLM = get_client(a.llm)
    print("loading city data…", flush=True)
    WORLD = build_world()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://localhost:{a.port}"
    print(f"TaskFlow-Travel running at {url}  ({len(WORLD.start_cities)} start cities, "
          f"{len(WORLD.destinations)} destinations; LLM: {LLM.label if LLM else 'offline'})  Ctrl+C to stop",
          flush=True)
    if not a.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
