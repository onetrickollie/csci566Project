# Results (test split)

Config: `{'seeds': [0, 1, 2], 'split': 'test', 'limit': None, 'skip_recovery': False, 'model_suffix': '', 'call_cap': 2, 'llm': 'offline', 'models': '3e2281036607'}`

git `e7c95ad` (uncommitted changes) · fingerprints `{'source': '09a45a79ca24', 'prompts': 'f9352f57f9ee', 'tasks': 'c6a92573e38a'}`

Rates are percentages. Learned systems: mean ± std over training seeds. LLM calls/tool calls/est. tokens come from the simulated cost model (see README).

Matched budget: at most 2 cost-model LLM calls per turn; a turn that would exceed it ends as BUDGET_EXHAUSTED with the plan as it is.

| System | Final pass | Revision success | New constr. sat. | Retention | Legacy unaffected preserved | Slots edited | Unneeded global | LLM calls/turn | Tool calls/turn | Est. tokens/turn |
|---|---|---|---|---|---|---|---|---|---|---|
| Always-Global | 17.4 | 19.4 | 35.4 | 83.7 | 100.0 | 0.0 | 0.0 | 0.00 | 0.00 | 0 |
| Always-Global (deterministic control) | 17.4 | 19.4 | 35.4 | 83.7 | 100.0 | 0.0 | 0.0 | 0.00 | 0.00 | 0 |
| Static rules | 96.7 | 98.1 | 99.4 | 99.0 | 96.3 | 18.3 | 0.0 | 0.89 | 0.67 | 1,376 |
| BC | 99.3 | 99.6 ± 0.1 | 100.0 | 99.9 ± 0.0 | 96.1 ± 0.0 | 18.6 | 0.0 | 0.72 ± 0.00 | 0.63 ± 0.00 | 1,106 |
| BC + augmentation | 99.8 ± 0.2 | 99.9 ± 0.1 | 100.0 | 100.0 ± 0.0 | 96.1 ± 0.0 | 18.6 ± 0.0 | 0.0 | 0.72 ± 0.00 | 0.63 ± 0.00 | 1,101 |
| BC + DAgger (1) | 99.6 ± 0.3 | 99.8 ± 0.1 | 100.0 | 100.0 | 96.1 ± 0.0 | 18.6 ± 0.0 | 0.0 | 0.71 ± 0.00 | 0.63 ± 0.00 | 1,102 |
| BC + DAgger (2) | 99.9 ± 0.2 | 100.0 ± 0.1 | 99.9 ± 0.1 | 100.0 | 96.1 ± 0.0 | 18.5 ± 0.0 | 0.0 | 0.72 ± 0.00 | 0.63 ± 0.00 | 1,100 |
| BC + DAgger (3) | 99.9 ± 0.2 | 99.9 ± 0.1 | 100.0 | 100.0 | 96.1 ± 0.0 | 18.6 | 0.0 | 0.72 ± 0.00 | 0.63 ± 0.00 | 1,102 |
| BC + aug + DAgger (3) | 99.4 ± 0.5 | 99.6 ± 0.3 | 99.9 ± 0.1 | 99.9 ± 0.1 | 96.1 ± 0.0 | 18.6 ± 0.0 | 0.0 | 0.72 ± 0.00 | 0.64 ± 0.01 | 1,103 |
| Deterministic scripted expert | 100.0 | 100.0 | 100.0 | 100.0 | 96.1 | 18.6 | 0.0 | 0.71 | 0.63 | 1,097 |

## Minimum necessary changes

Exact minimum slot edits over complete feasible plans. Scored only on successful feasible turns; read alongside revision success and the scored-turn count. Budget turns include all costed slots. Optimal preservation = 1 − excess edits / (13 − minimum edits); undefined when all 13 must change. The legacy unaffected-slot metric above is retained for comparison.

| System | Scored turns (mean) | Minimum edits | Excess edits | Optimal preservation % |
|---|---|---|---|---|
| Always-Global | 134 | 0.00 | 0.00 | 100.0 |
| Always-Global (deterministic control) | 134 | 0.00 | 0.00 | 100.0 |
| Static rules | 547 | 1.20 | 1.14 | 89.9 |
| BC | 559.333 | 1.26 ± 0.00 | 1.16 ± 0.00 | 89.6 ± 0.0 |
| BC + augmentation | 559.667 | 1.25 ± 0.00 | 1.16 ± 0.00 | 89.7 ± 0.0 |
| BC + DAgger (1) | 560 | 1.26 | 1.16 ± 0.00 | 89.6 ± 0.0 |
| BC + DAgger (2) | 559.667 | 1.25 ± 0.00 | 1.16 ± 0.00 | 89.6 ± 0.0 |
| BC + DAgger (3) | 560 | 1.26 | 1.16 | 89.7 |
| BC + aug + DAgger (3) | 557.667 | 1.26 ± 0.00 | 1.16 ± 0.00 | 89.6 ± 0.0 |
| Deterministic scripted expert | 560 | 1.26 | 1.16 | 89.7 |

## Clarification behaviour

| System | Recall on infeasible updates | Precision | Timeouts | Budget exhausted |
|---|---|---|---|---|
| Always-Global | 0.0 | – | 0.0 | 100.0 |
| Always-Global (deterministic control) | 0.0 | – | 0.0 | 100.0 |
| Static rules | 100.0 | 100.0 | 0.0 | 1.9 |
| BC | 98.4 | 99.5 ± 0.4 | 0.0 ± 0.1 | 0.2 ± 0.1 |
| BC + augmentation | 99.7 ± 0.4 | 100.0 | 0.0 | 0.1 ± 0.1 |
| BC + DAgger (1) | 99.0 ± 0.4 | 100.0 | 0.0 | 0.1 ± 0.1 |
| BC + DAgger (2) | 100.0 | 100.0 | 0.0 | 0.0 |
| BC + DAgger (3) | 99.5 ± 0.4 | 100.0 | 0.0 | 0.0 ± 0.1 |
| BC + aug + DAgger (3) | 99.5 ± 0.4 | 99.5 ± 0.7 | 0.0 ± 0.1 | 0.0 ± 0.1 |
| Deterministic scripted expert | 100.0 | 100.0 | 0.0 | 0.0 |

## Recovery from a forced mistake (164 episodes whose first update needs a repair)

The listed action is forced as the first step of the turn; the coordinator then continues. Cell = turn success % over all selected episodes / over the episodes where the forced action left the plan broken (n), then LLM calls. Mistakes that already fix the plan (e.g. a global rebuild) say nothing about recovery.

| System | REPLAN_LOCAL_ACCOMMODATION | REPLAN_LOCAL_TRANSPORT | REPLAN_LOCAL_MEALS | REPLAN_GLOBAL |
|---|---|---|---|---|
| Always-Global | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| Always-Global (deterministic control) | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| Static rules | 99.4 / 99.3 (n=141), 1.92 | 99.4 / 99.4 (n=164), 2.00 | 99.4 / 99.1 (n=116), 2.00 | 0.0 / – (n=0), 0.00 |
| BC | 96.3 / 95.7 (n=141), 1.83 | 92.3 / 92.3 (n=164), 1.97 | 85.6 / 79.6 (n=116), 1.66 | 0.0 / – (n=0), 0.00 |
| BC + augmentation | 99.4 / 99.3 (n=141), 1.86 | 99.2 / 99.2 (n=164), 2.00 | 99.2 / 98.9 (n=116), 1.71 | 0.0 / – (n=0), 0.00 |
| BC + DAgger (1) | 99.0 / 98.8 (n=141), 1.86 | 88.6 / 88.6 (n=164), 2.00 | 88.6 / 83.9 (n=116), 1.71 | 0.0 / – (n=0), 0.00 |
| BC + DAgger (2) | 98.8 / 98.6 (n=141), 1.86 | 89.8 / 89.8 (n=164), 2.00 | 91.5 / 87.9 (n=116), 1.71 | 0.0 / – (n=0), 0.00 |
| BC + DAgger (3) | 99.4 / 99.3 (n=141), 1.86 | 96.1 / 96.1 (n=164), 2.00 | 95.3 / 93.4 (n=116), 1.71 | 0.0 / – (n=0), 0.00 |
| BC + aug + DAgger (3) | 99.4 / 99.3 (n=141), 1.86 | 99.4 / 99.4 (n=164), 2.00 | 99.0 / 98.6 (n=116), 1.71 | 0.0 / – (n=0), 0.00 |
| Deterministic scripted expert | 99.4 / 99.3 (n=141), 1.86 | 99.4 / 99.4 (n=164), 2.00 | 99.4 / 99.1 (n=116), 1.71 | 0.0 / – (n=0), 0.00 |

## By update type

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | add | delete | replace | reprioritize |
|---|---|---|---|---|
| Always-Global | 15.0 / 100 | 67.3 / 100 | 7.8 / 100 | 32.9 / 100 |
| Always-Global (deterministic control) | 15.0 / 100 | 67.3 / 100 | 7.8 / 100 | 32.9 / 100 |
| Static rules | 97.9 / 95 | 100.0 / 100 | 98.0 / 100 | 98.6 / 100 |
| BC | 99.8 / 95 | 100.0 / 100 | 100.0 / 100 | 98.6 / 100 |
| BC + augmentation | 100.0 / 95 | 100.0 / 100 | 100.0 / 100 | 98.6 / 100 |
| BC + DAgger (1) | 99.8 / 95 | 100.0 / 100 | 100.0 / 100 | 98.6 / 100 |
| BC + DAgger (2) | 100.0 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + DAgger (3) | 100.0 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + aug + DAgger (3) | 99.6 / 95 | 98.0 / 99 | 99.0 / 100 | 98.6 / 100 |
| Deterministic scripted expert | 100.0 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |

## By turn position (4th turn only exists in test)

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | held-out (4th turn) | turn 1 | turn 2 | turn 3 |
|---|---|---|---|---|
| Always-Global | 14.5 / 100 | 23.9 / 100 | 18.1 / 100 | 14.9 / 100 |
| Always-Global (deterministic control) | 14.5 / 100 | 23.9 / 100 | 18.1 / 100 | 14.9 / 100 |
| Static rules | 94.2 / 97 | 99.6 / 96 | 97.1 / 96 | 98.5 / 97 |
| BC | 98.6 / 97 | 100.0 / 96 | 100.0 / 96 | 99.3 / 97 |
| BC + augmentation | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 99.3 / 97 |
| BC + DAgger (1) | 98.6 / 97 | 100.0 / 96 | 100.0 / 96 | 99.3 / 97 |
| BC + DAgger (2) | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC + DAgger (3) | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC + aug + DAgger (3) | 97.1 / 96 | 100.0 / 96 | 99.5 / 96 | 98.5 / 97 |
| Deterministic scripted expert | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |

## Figures

![pareto](pareto.png)

![error](error_vs_step.png)

![recovery](recovery.png)
