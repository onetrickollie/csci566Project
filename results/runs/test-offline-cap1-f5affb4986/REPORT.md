# Results (test split)

Config: `{'seeds': [0, 1, 2], 'split': 'test', 'limit': None, 'skip_recovery': False, 'model_suffix': '', 'call_cap': 1, 'llm': 'offline', 'models': '3e2281036607'}`

git `e7c95ad` (uncommitted changes) · fingerprints `{'source': '09a45a79ca24', 'prompts': 'f9352f57f9ee', 'tasks': 'c6a92573e38a'}`

Rates are percentages. Learned systems: mean ± std over training seeds. LLM calls/tool calls/est. tokens come from the simulated cost model (see README).

Matched budget: at most 1 cost-model LLM calls per turn; a turn that would exceed it ends as BUDGET_EXHAUSTED with the plan as it is.

| System | Final pass | Revision success | New constr. sat. | Retention | Legacy unaffected preserved | Slots edited | Unneeded global | LLM calls/turn | Tool calls/turn | Est. tokens/turn |
|---|---|---|---|---|---|---|---|---|---|---|
| Always-Global | 17.4 | 19.4 | 35.4 | 83.7 | 100.0 | 0.0 | 0.0 | 0.00 | 0.00 | 0 |
| Always-Global (deterministic control) | 17.4 | 19.4 | 35.4 | 83.7 | 100.0 | 0.0 | 0.0 | 0.00 | 0.00 | 0 |
| Static rules | 65.6 | 72.4 | 98.4 | 94.8 | 96.5 | 18.3 | 0.0 | 0.76 | 0.71 | 1,398 |
| BC | 96.7 ± 0.3 | 97.9 ± 0.3 | 100.0 | 98.9 ± 0.1 | 96.3 | 18.5 | 0.0 | 0.70 ± 0.00 | 0.63 ± 0.00 | 1,088 |
| BC + augmentation | 97.0 ± 0.2 | 97.9 ± 0.2 | 99.9 ± 0.1 | 99.0 ± 0.0 | 96.3 | 18.4 ± 0.0 | 0.0 | 0.70 ± 0.00 | 0.63 ± 0.00 | 1,089 |
| BC + DAgger (1) | 97.2 ± 0.2 | 98.2 ± 0.1 | 100.0 | 99.0 ± 0.0 | 96.3 ± 0.0 | 18.5 ± 0.0 | 0.0 | 0.70 ± 0.00 | 0.63 ± 0.01 | 1,085 |
| BC + DAgger (2) | 97.1 ± 0.3 | 98.1 ± 0.2 | 99.9 ± 0.1 | 99.0 ± 0.0 | 96.3 | 18.4 ± 0.0 | 0.0 | 0.70 ± 0.00 | 0.63 ± 0.00 | 1,085 |
| BC + DAgger (3) | 97.0 ± 0.2 | 98.0 ± 0.1 | 100.0 | 99.0 ± 0.0 | 96.3 | 18.5 | 0.0 | 0.70 ± 0.00 | 0.63 ± 0.00 | 1,087 |
| BC + aug + DAgger (3) | 96.7 ± 0.5 | 97.9 ± 0.3 | 99.7 ± 0.2 | 99.0 ± 0.1 | 96.3 ± 0.0 | 18.4 ± 0.0 | 0.0 | 0.70 ± 0.00 | 0.64 ± 0.01 | 1,089 |
| Deterministic scripted expert | 97.8 | 98.5 | 99.6 | 99.1 | 96.4 | 18.3 | 0.0 | 0.70 | 0.63 | 1,082 |

## Minimum necessary changes

Exact minimum slot edits over complete feasible plans. Scored only on successful feasible turns; read alongside revision success and the scored-turn count. Budget turns include all costed slots. Optimal preservation = 1 − excess edits / (13 − minimum edits); undefined when all 13 must change. The legacy unaffected-slot metric above is retained for comparison.

| System | Scored turns (mean) | Minimum edits | Excess edits | Optimal preservation % |
|---|---|---|---|---|
| Always-Global | 134 | 0.00 | 0.00 | 100.0 |
| Always-Global (deterministic control) | 134 | 0.00 | 0.00 | 100.0 |
| Static rules | 499 | 1.23 | 1.17 | 89.6 |
| BC | 549 | 1.21 ± 0.00 | 1.15 ± 0.00 | 89.8 ± 0.0 |
| BC + augmentation | 549.333 | 1.21 ± 0.00 | 1.15 ± 0.00 | 89.8 ± 0.0 |
| BC + DAgger (1) | 549.667 | 1.20 ± 0.00 | 1.15 ± 0.00 | 89.8 ± 0.0 |
| BC + DAgger (2) | 549 | 1.21 ± 0.00 | 1.15 ± 0.00 | 89.8 ± 0.0 |
| BC + DAgger (3) | 549.333 | 1.21 ± 0.00 | 1.15 ± 0.00 | 89.8 ± 0.0 |
| BC + aug + DAgger (3) | 548 | 1.21 ± 0.00 | 1.15 ± 0.00 | 89.7 ± 0.0 |
| Deterministic scripted expert | 550 | 1.20 | 1.15 | 89.8 |

## Clarification behaviour

| System | Recall on infeasible updates | Precision | Timeouts | Budget exhausted |
|---|---|---|---|---|
| Always-Global | 0.0 | – | 0.0 | 100.0 |
| Always-Global (deterministic control) | 0.0 | – | 0.0 | 100.0 |
| Static rules | 0.0 | 0.0 | 0.0 | 29.5 |
| BC | 97.4 ± 1.0 | 99.5 ± 0.4 | 0.0 | 2.0 ± 0.2 |
| BC + augmentation | 96.9 ± 1.1 | 100.0 | 0.0 | 2.1 ± 0.2 |
| BC + DAgger (1) | 98.4 | 99.7 ± 0.4 | 0.0 | 1.7 ± 0.1 |
| BC + DAgger (2) | 98.4 ± 0.6 | 99.2 ± 0.6 | 0.0 | 1.7 ± 0.1 |
| BC + DAgger (3) | 97.7 ± 0.6 | 99.5 ± 0.4 | 0.0 | 1.8 ± 0.1 |
| BC + aug + DAgger (3) | 97.9 ± 0.4 | 99.2 ± 0.6 | 0.0 ± 0.1 | 1.7 ± 0.1 |
| Deterministic scripted expert | 100.0 | 100.0 | 0.0 | 1.5 |

## Recovery from a forced mistake (164 episodes whose first update needs a repair)

The listed action is forced as the first step of the turn; the coordinator then continues. Cell = turn success % over all selected episodes / over the episodes where the forced action left the plan broken (n), then LLM calls. Mistakes that already fix the plan (e.g. a global rebuild) say nothing about recovery.

| System | REPLAN_LOCAL_ACCOMMODATION | REPLAN_LOCAL_TRANSPORT | REPLAN_LOCAL_MEALS | REPLAN_GLOBAL |
|---|---|---|---|---|
| Always-Global | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| Always-Global (deterministic control) | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| Static rules | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| BC | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| BC + augmentation | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| BC + DAgger (1) | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| BC + DAgger (2) | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| BC + DAgger (3) | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| BC + aug + DAgger (3) | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |
| Deterministic scripted expert | 14.0 / 0.0 (n=141), 1.00 | 0.0 / 0.0 (n=164), 1.00 | 29.3 / 0.0 (n=116), 1.00 | 0.0 / – (n=0), 0.00 |

## By update type

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | add | delete | replace | reprioritize |
|---|---|---|---|---|
| Always-Global | 15.0 / 100 | 67.3 / 100 | 7.8 / 100 | 32.9 / 100 |
| Always-Global (deterministic control) | 15.0 / 100 | 67.3 / 100 | 7.8 / 100 | 32.9 / 100 |
| Static rules | 76.7 / 95 | 75.5 / 100 | 58.8 / 100 | 61.4 / 100 |
| BC | 97.6 / 95 | 100.0 / 100 | 99.0 / 100 | 98.6 / 100 |
| BC + augmentation | 96.8 / 95 | 98.0 / 100 | 100.0 / 100 | 98.6 / 100 |
| BC + DAgger (1) | 97.6 / 95 | 100.0 / 100 | 100.0 / 100 | 98.6 / 100 |
| BC + DAgger (2) | 97.2 / 95 | 98.0 / 100 | 99.0 / 100 | 100.0 / 100 |
| BC + DAgger (3) | 97.4 / 95 | 98.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + aug + DAgger (3) | 97.4 / 95 | 95.9 / 99 | 99.0 / 100 | 98.6 / 100 |
| Deterministic scripted expert | 97.9 / 95 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |

## By turn position (4th turn only exists in test)

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | held-out (4th turn) | turn 1 | turn 2 | turn 3 |
|---|---|---|---|---|
| Always-Global | 14.5 / 100 | 23.9 / 100 | 18.1 / 100 | 14.9 / 100 |
| Always-Global (deterministic control) | 14.5 / 100 | 23.9 / 100 | 18.1 / 100 | 14.9 / 100 |
| Static rules | 52.2 / 98 | 83.0 / 96 | 72.4 / 96 | 61.2 / 98 |
| BC | 95.7 / 97 | 99.6 / 96 | 96.7 / 96 | 98.5 / 97 |
| BC + augmentation | 94.2 / 97 | 99.6 / 96 | 96.7 / 96 | 96.3 / 97 |
| BC + DAgger (1) | 95.7 / 97 | 99.6 / 96 | 97.1 / 96 | 98.5 / 97 |
| BC + DAgger (2) | 92.8 / 97 | 99.6 / 96 | 96.7 / 96 | 98.5 / 97 |
| BC + DAgger (3) | 94.2 / 97 | 99.6 / 96 | 96.7 / 96 | 99.3 / 97 |
| BC + aug + DAgger (3) | 92.8 / 96 | 99.6 / 96 | 96.7 / 96 | 97.8 / 97 |
| Deterministic scripted expert | 97.1 / 98 | 99.6 / 96 | 97.1 / 96 | 99.3 / 97 |

## Figures

![pareto](pareto.png)

![error](error_vs_step.png)

![recovery](recovery.png)
