# Results (test split)

Config: `{'seeds': [0, 1, 2], 'split': 'test', 'limit': None, 'skip_recovery': False, 'model_suffix': '', 'call_cap': None, 'llm': 'offline', 'models': '4ec8bf2206a9'}`

git `50777f0` · fingerprints `{'source': '76eebacf7b66', 'prompts': 'f9352f57f9ee', 'tasks': '31cf06aeb6b9'}`

Rates are percentages. Learned systems: mean ± std over training seeds. LLM calls/tool calls/est. tokens come from the simulated cost model (see README).

| System | Final pass | Revision success | New constr. sat. | Retention | Legacy unaffected preserved | Slots edited | Unneeded global | LLM calls/turn | Tool calls/turn | Est. tokens/turn |
|---|---|---|---|---|---|---|---|---|---|---|
| Always-Global | 100.0 | 100.0 | 100.0 | 100.0 | 31.3 | 73.1 | 48.5 | 4.19 | 3.00 | 6,056 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 100.0 | 100.0 | 93.1 | 21.2 | 50.7 | 4.19 | 3.00 | 6,056 |
| Static rules | 100.0 | 100.0 | 100.0 | 100.0 | 95.4 | 18.9 | 1.6 | 0.95 | 0.71 | 1,464 |
| Static rules (cost-aware) | 100.0 | 100.0 | 100.0 | 100.0 | 96.1 | 18.6 | 0.0 | 0.84 | 0.64 | 1,291 |
| BC | 99.4 ± 0.3 | 99.7 ± 0.2 | 99.9 ± 0.1 | 100.0 ± 0.0 | 96.1 ± 0.0 | 18.6 ± 0.0 | 0.0 | 0.72 ± 0.01 | 0.63 ± 0.00 | 1,117 |
| BC + augmentation | 100.0 | 100.0 | 100.0 | 100.0 | 96.1 ± 0.0 | 18.6 ± 0.0 | 0.0 | 0.72 ± 0.01 | 0.63 ± 0.00 | 1,110 |
| BC + DAgger (1) | 99.6 ± 0.5 | 99.8 ± 0.3 | 99.9 ± 0.1 | 100.0 ± 0.0 | 96.1 | 18.6 ± 0.0 | 0.0 | 0.72 ± 0.01 | 0.63 ± 0.00 | 1,111 |
| BC + DAgger (2) | 100.0 | 100.0 | 100.0 | 100.0 | 96.1 ± 0.0 | 18.6 ± 0.0 | 0.0 | 0.72 ± 0.00 | 0.63 ± 0.00 | 1,104 |
| BC + DAgger (3) | 99.5 ± 0.3 | 99.6 ± 0.3 | 99.8 ± 0.2 | 99.9 ± 0.1 | 96.0 ± 0.0 | 18.7 ± 0.1 | 0.0 | 0.72 ± 0.00 | 0.63 ± 0.00 | 1,106 |
| BC + aug + DAgger (3) | 99.8 ± 0.2 | 99.6 ± 0.1 | 99.8 | 99.9 ± 0.0 | 96.0 ± 0.0 | 18.7 ± 0.0 | 0.0 | 0.72 ± 0.00 | 0.64 ± 0.00 | 1,109 |
| Deterministic scripted expert | 100.0 | 100.0 | 100.0 | 100.0 | 96.1 | 18.6 | 0.0 | 0.71 | 0.63 | 1,097 |

## Minimum necessary changes

Exact minimum slot edits over complete feasible plans. Scored only on successful feasible turns; read alongside revision success and the scored-turn count. Budget turns include all costed slots. Optimal preservation = 1 − excess edits / (13 − minimum edits); undefined when all 13 must change. The legacy unaffected-slot metric above is retained for comparison.

| System | Scored turns (mean) | Minimum edits | Excess edits | Optimal preservation % |
|---|---|---|---|---|
| Always-Global | 560 | 1.28 | 8.22 | 30.0 |
| Always-Global (deterministic control) | 560 | 1.24 | 1.52 | 86.9 |
| Static rules | 560 | 1.25 | 1.21 | 89.0 |
| Static rules (cost-aware) | 560 | 1.26 | 1.16 | 89.7 |
| BC | 559.333 | 1.26 ± 0.00 | 1.16 ± 0.00 | 89.6 ± 0.0 |
| BC + augmentation | 560 | 1.26 | 1.16 ± 0.00 | 89.6 ± 0.0 |
| BC + DAgger (1) | 559 | 1.26 ± 0.00 | 1.17 ± 0.00 | 89.6 ± 0.0 |
| BC + DAgger (2) | 560 | 1.26 | 1.16 ± 0.00 | 89.6 ± 0.0 |
| BC + DAgger (3) | 557 | 1.26 ± 0.00 | 1.17 ± 0.00 | 89.6 ± 0.0 |
| BC + aug + DAgger (3) | 557.333 | 1.26 ± 0.00 | 1.17 ± 0.01 | 89.5 ± 0.1 |
| Deterministic scripted expert | 560 | 1.26 | 1.16 | 89.7 |

## Clarification behaviour

| System | Recall on infeasible updates | Precision | Timeouts | Budget exhausted |
|---|---|---|---|---|
| Always-Global | 100.0 | 100.0 | 0.0 | 0.0 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 0.0 | 0.0 |
| Static rules | 100.0 | 100.0 | 0.0 | 0.0 |
| Static rules (cost-aware) | 100.0 | 100.0 | 0.0 | 0.0 |
| BC | 99.0 ± 0.4 | 99.7 ± 0.4 | 0.2 ± 0.1 | 0.0 |
| BC + augmentation | 100.0 | 100.0 | 0.1 ± 0.1 | 0.0 |
| BC + DAgger (1) | 99.5 ± 0.7 | 99.7 ± 0.4 | 0.0 ± 0.1 | 0.0 |
| BC + DAgger (2) | 100.0 | 100.0 | 0.0 | 0.0 |
| BC + DAgger (3) | 100.0 | 99.0 ± 0.9 | 0.0 | 0.0 |
| BC + aug + DAgger (3) | 100.0 | 99.5 ± 0.4 | 0.0 | 0.0 |
| Deterministic scripted expert | 100.0 | 100.0 | 0.0 | 0.0 |

## Recovery from a forced mistake (164 episodes whose first update needs a repair)

The listed action is forced as the first step of the turn; the coordinator then continues. Cell = turn success % over all selected episodes / over the episodes where the forced action left the plan broken (n), then LLM calls. Mistakes that already fix the plan (e.g. a global rebuild) say nothing about recovery.

| System | REPLAN_LOCAL_ACCOMMODATION | REPLAN_LOCAL_TRANSPORT | REPLAN_LOCAL_MEALS | REPLAN_GLOBAL |
|---|---|---|---|---|
| Always-Global | 100.0 / 100.0 (n=141), 5.00 | 100.0 / 100.0 (n=164), 5.00 | 100.0 / 100.0 (n=116), 5.00 | 100.0 / – (n=0), 4.00 |
| Always-Global (deterministic control) | 100.0 / 100.0 (n=141), 5.00 | 100.0 / 100.0 (n=164), 5.00 | 100.0 / 100.0 (n=116), 5.00 | 100.0 / – (n=0), 4.00 |
| Static rules | 100.0 / 100.0 (n=141), 1.95 | 100.0 / 100.0 (n=164), 2.02 | 100.0 / 100.0 (n=116), 2.02 | 100.0 / – (n=0), 5.00 |
| Static rules (cost-aware) | 100.0 / 100.0 (n=141), 1.88 | 100.0 / 100.0 (n=164), 2.01 | 100.0 / 100.0 (n=116), 1.71 | 100.0 / – (n=0), 4.00 |
| BC | 95.9 / 95.3 (n=141), 1.83 | 95.7 / 95.7 (n=164), 2.05 | 93.3 / 90.5 (n=116), 1.93 | 100.0 / – (n=0), 4.00 |
| BC + augmentation | 100.0 / 100.0 (n=141), 1.87 | 100.0 / 100.0 (n=164), 2.01 | 99.4 / 99.1 (n=116), 1.76 | 100.0 / – (n=0), 4.00 |
| BC + DAgger (1) | 100.0 / 100.0 (n=141), 1.87 | 93.1 / 93.1 (n=164), 2.05 | 96.5 / 95.1 (n=116), 1.82 | 100.0 / – (n=0), 4.00 |
| BC + DAgger (2) | 100.0 / 100.0 (n=141), 1.87 | 92.7 / 92.7 (n=164), 2.03 | 97.0 / 95.7 (n=116), 1.73 | 100.0 / – (n=0), 4.00 |
| BC + DAgger (3) | 100.0 / 100.0 (n=141), 1.87 | 94.7 / 94.7 (n=164), 2.06 | 87.8 / 82.8 (n=116), 1.87 | 100.0 / – (n=0), 4.00 |
| BC + aug + DAgger (3) | 100.0 / 100.0 (n=141), 1.87 | 100.0 / 100.0 (n=164), 2.01 | 99.4 / 99.1 (n=116), 1.73 | 100.0 / – (n=0), 4.00 |
| Deterministic scripted expert | 100.0 / 100.0 (n=141), 1.87 | 100.0 / 100.0 (n=164), 2.01 | 100.0 / 100.0 (n=116), 1.71 | 100.0 / – (n=0), 4.00 |

## By update type

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | add | delete | replace | reprioritize |
|---|---|---|---|---|
| Always-Global | 100.0 / 33 | 100.0 / 25 | 100.0 / 31 | 100.0 / 21 |
| Always-Global (deterministic control) | 100.0 / 93 | 100.0 / 83 | 100.0 / 98 | 100.0 / 99 |
| Static rules | 100.0 / 94 | 100.0 / 100 | 100.0 / 98 | 100.0 / 100 |
| Static rules (cost-aware) | 100.0 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC | 99.8 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + augmentation | 100.0 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + DAgger (1) | 100.0 / 94 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + DAgger (2) | 100.0 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + DAgger (3) | 99.6 / 95 | 98.0 / 99 | 98.0 / 100 | 100.0 / 100 |
| BC + aug + DAgger (3) | 99.8 / 95 | 98.0 / 99 | 99.0 / 100 | 100.0 / 100 |
| Deterministic scripted expert | 100.0 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |

## By turn position (4th turn only exists in test)

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | held-out (4th turn) | turn 1 | turn 2 | turn 3 |
|---|---|---|---|---|
| Always-Global | 100.0 / 35 | 100.0 / 31 | 100.0 / 29 | 100.0 / 33 |
| Always-Global (deterministic control) | 100.0 / 89 | 100.0 / 94 | 100.0 / 94 | 100.0 / 93 |
| Static rules | 100.0 / 96 | 100.0 / 95 | 100.0 / 95 | 100.0 / 96 |
| Static rules (cost-aware) | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC | 98.6 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC + augmentation | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC + DAgger (1) | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC + DAgger (2) | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |
| BC + DAgger (3) | 97.1 / 96 | 100.0 / 96 | 99.5 / 96 | 98.5 / 97 |
| BC + aug + DAgger (3) | 98.6 / 96 | 100.0 / 96 | 99.5 / 96 | 99.3 / 97 |
| Deterministic scripted expert | 100.0 / 97 | 100.0 / 96 | 100.0 / 96 | 100.0 / 97 |

## Figures

![pareto](pareto.png)

![error](error_vs_step.png)

![recovery](recovery.png)
