# Results (test split)

Config: `{'seeds': [0, 1, 2], 'split': 'test', 'limit': None, 'skip_recovery': False, 'model_suffix': '', 'call_cap': None, 'llm': 'offline', 'models': 'b256bcc46c15'}`

git `b98e383` (uncommitted changes) · fingerprints `{'source': 'fe9eae875cb6', 'prompts': 'f9352f57f9ee', 'tasks': '3753a97fdb1e'}`

Rates are percentages. Learned systems: mean ± std over training seeds. LLM calls/tool calls/est. tokens come from the simulated cost model (see README).

| System | Final pass | Revision success | New constr. sat. | Retention | Unaffected preserved | Slots edited | Unneeded global | LLM calls/turn | Tool calls/turn | Est. tokens/turn |
|---|---|---|---|---|---|---|---|---|---|---|
| Always-Global | 100.0 | 100.0 | 100.0 | 100.0 | 31.3 | 73.1 | 48.5 | 4.19 | 3.00 | 6,056 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 100.0 | 100.0 | 93.1 | 21.2 | 50.7 | 4.19 | 3.00 | 6,056 |
| Static rules | 100.0 | 100.0 | 100.0 | 100.0 | 95.4 | 18.9 | 1.6 | 0.95 | 0.71 | 1,464 |
| BC | 97.5 ± 1.5 | 98.6 ± 0.8 | 98.8 ± 0.7 | 99.9 ± 0.1 | 96.3 ± 0.1 | 18.1 ± 0.2 | 0.0 | 0.73 ± 0.01 | 0.64 ± 0.01 | 1,112 |
| BC + augmentation | 99.9 ± 0.2 | 100.0 ± 0.1 | 100.0 | 100.0 | 96.1 ± 0.0 | 18.6 ± 0.1 | 0.0 | 0.72 ± 0.00 | 0.63 ± 0.00 | 1,106 |
| BC + DAgger (1) | 99.9 ± 0.2 | 100.0 ± 0.1 | 99.9 ± 0.1 | 100.0 | 96.1 ± 0.0 | 18.5 ± 0.0 | 0.0 | 0.72 ± 0.00 | 0.64 ± 0.00 | 1,103 |
| BC + DAgger (2) | 99.9 ± 0.2 | 100.0 ± 0.1 | 100.0 | 100.0 | 96.1 ± 0.0 | 18.6 ± 0.0 | 0.0 | 0.72 ± 0.00 | 0.64 ± 0.00 | 1,108 |
| BC + DAgger (3) | 99.9 ± 0.2 | 100.0 ± 0.1 | 100.0 | 100.0 | 96.1 ± 0.0 | 18.6 ± 0.0 | 0.0 | 0.72 ± 0.00 | 0.63 ± 0.00 | 1,105 |
| BC + aug + DAgger (3) | 99.9 ± 0.2 | 100.0 ± 0.1 | 99.9 ± 0.1 | 100.0 | 96.1 ± 0.0 | 18.6 ± 0.1 | 0.0 | 0.72 ± 0.00 | 0.64 ± 0.00 | 1,112 |
| Privileged oracle (upper bound) | 100.0 | 100.0 | 100.0 | 100.0 | 96.1 | 18.6 | 0.0 | 0.71 | 0.63 | 1,097 |

## Clarification behaviour

| System | Recall on infeasible updates | Precision | Timeouts | Budget exhausted |
|---|---|---|---|---|
| Always-Global | 100.0 | 100.0 | 0.0 | 0.0 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 0.0 | 0.0 |
| Static rules | 100.0 | 100.0 | 0.0 | 0.0 |
| BC | 99.0 ± 1.0 | 95.3 ± 2.8 | 0.2 ± 0.2 | 0.0 |
| BC + augmentation | 99.7 ± 0.4 | 100.0 | 0.0 | 0.0 |
| BC + DAgger (1) | 100.0 | 100.0 | 0.0 | 0.0 |
| BC + DAgger (2) | 99.7 ± 0.4 | 100.0 | 0.0 ± 0.1 | 0.0 |
| BC + DAgger (3) | 99.7 ± 0.4 | 100.0 | 0.0 | 0.0 |
| BC + aug + DAgger (3) | 100.0 | 100.0 | 0.0 ± 0.1 | 0.0 |
| Privileged oracle (upper bound) | 100.0 | 100.0 | 0.0 | 0.0 |

## Recovery from a forced mistake (164 episodes whose first update needs a repair)

The listed action is forced as the first step of the turn; the coordinator then continues. Cell = turn success % over all selected episodes / over the episodes where the forced action left the plan broken (n), then LLM calls. Mistakes that already fix the plan (e.g. a global rebuild) say nothing about recovery.

| System | REPLAN_LOCAL_ACCOMMODATION | REPLAN_LOCAL_TRANSPORT | REPLAN_LOCAL_MEALS | REPLAN_GLOBAL |
|---|---|---|---|---|
| Always-Global | 100.0 / 100.0 (n=141), 5.00 | 100.0 / 100.0 (n=164), 5.00 | 100.0 / 100.0 (n=116), 5.00 | 100.0 / – (n=0), 4.00 |
| Always-Global (deterministic control) | 100.0 / 100.0 (n=141), 5.00 | 100.0 / 100.0 (n=164), 5.00 | 100.0 / 100.0 (n=116), 5.00 | 100.0 / – (n=0), 4.00 |
| Static rules | 100.0 / 100.0 (n=141), 1.95 | 100.0 / 100.0 (n=164), 2.02 | 100.0 / 100.0 (n=116), 2.02 | 100.0 / – (n=0), 5.00 |
| BC | 90.0 / 88.4 (n=141), 1.78 | 82.7 / 82.7 (n=164), 2.05 | 89.0 / 84.5 (n=116), 1.72 | 100.0 / – (n=0), 4.00 |
| BC + augmentation | 100.0 / 100.0 (n=141), 1.87 | 100.0 / 100.0 (n=164), 2.01 | 100.0 / 100.0 (n=116), 1.71 | 100.0 / – (n=0), 4.00 |
| BC + DAgger (1) | 94.7 / 93.9 (n=141), 1.81 | 92.3 / 92.3 (n=164), 2.16 | 89.6 / 85.3 (n=116), 1.74 | 100.0 / – (n=0), 4.00 |
| BC + DAgger (2) | 99.4 / 99.3 (n=141), 1.86 | 93.7 / 93.7 (n=164), 2.06 | 92.7 / 89.7 (n=116), 1.75 | 100.0 / – (n=0), 4.00 |
| BC + DAgger (3) | 99.2 / 99.1 (n=141), 1.86 | 97.4 / 97.4 (n=164), 2.04 | 93.7 / 91.1 (n=116), 1.73 | 100.0 / – (n=0), 4.00 |
| BC + aug + DAgger (3) | 100.0 / 100.0 (n=141), 1.87 | 100.0 / 100.0 (n=164), 2.01 | 100.0 / 100.0 (n=116), 1.71 | 100.0 / – (n=0), 4.00 |
| Privileged oracle (upper bound) | 100.0 / 100.0 (n=141), 1.87 | 100.0 / 100.0 (n=164), 2.01 | 100.0 / 100.0 (n=116), 1.71 | 100.0 / – (n=0), 4.00 |

## By update type

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | add | delete | replace | reprioritize |
|---|---|---|---|---|
| Always-Global | 100.0 / 33 | 100.0 / 25 | 100.0 / 31 | 100.0 / 21 |
| Always-Global (deterministic control) | 100.0 / 93 | 100.0 / 83 | 100.0 / 98 | 100.0 / 99 |
| Static rules | 100.0 / 94 | 100.0 / 100 | 100.0 / 98 | 100.0 / 100 |
| BC | 97.4 / 95 | 98.0 / 100 | 100.0 / 100 | 97.1 / 100 |
| BC + augmentation | 100.0 / 94 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + DAgger (1) | 100.0 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + DAgger (2) | 99.8 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + DAgger (3) | 100.0 / 94 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + aug + DAgger (3) | 100.0 / 94 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| Privileged oracle (upper bound) | 100.0 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |

## By turn position (4th turn only exists in test)

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | held-out (4th turn) | turn 1 | turn 2 | turn 3 |
|---|---|---|---|---|
| Always-Global | 100.0 / 35 | 100.0 / 31 | 100.0 / 29 | 100.0 / 33 |
| Always-Global (deterministic control) | 100.0 / 89 | 100.0 / 94 | 100.0 / 94 | 100.0 / 93 |
| Static rules | 100.0 / 96 | 100.0 / 95 | 100.0 / 95 | 100.0 / 96 |
| BC | 92.8 / 97 | 100.0 / 96 | 97.6 / 96 | 96.3 / 98 |
| BC + augmentation | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC + DAgger (1) | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC + DAgger (2) | 98.6 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC + DAgger (3) | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC + aug + DAgger (3) | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| Privileged oracle (upper bound) | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |

## Figures

![pareto](pareto.png)

![error](error_vs_step.png)

![recovery](recovery.png)
