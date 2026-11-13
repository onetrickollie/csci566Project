# Results (val split)

Config: `{'seeds': [0], 'split': 'val', 'limit': 30, 'skip_recovery': True, 'model_suffix': '', 'call_cap': None, 'llm': {'provider': 'fake', 'model': 'fake', 'endpoint': 'local://fake', 'temperature': 0.0}, 'models': 'd6245b50cd4c'}`

git `b98e383` (uncommitted changes) · fingerprints `{'source': 'fe9eae875cb6', 'prompts': 'f9352f57f9ee', 'tasks': '3753a97fdb1e'}`

Rates are percentages. Learned systems: mean ± std over training seeds. LLM calls/tool calls/est. tokens come from the simulated cost model (see README); measured columns come from the live client.

| System | Final pass | Revision success | New constr. sat. | Retention | Unaffected preserved | Slots edited | Unneeded global | LLM calls/turn | Tool calls/turn | Est. tokens/turn | Measured LLM requests/turn | Measured tokens/turn |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Always-Global | 100.0 | 100.0 | 100.0 | 100.0 | 92.6 | 28.4 | 63.5 | 4.17 | 3.00 | 6,052 | 4.98 | 1,173 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 100.0 | 100.0 | 92.6 | 28.4 | 63.5 | 4.17 | 3.00 | 6,052 | 4.98 | 1,173 |
| Static rules | 100.0 | 100.0 | 100.0 | 100.0 | 96.9 | 24.4 | 3.2 | 1.11 | 0.89 | 1,775 | 1.92 | 460 |
| LLM coordinator | 100.0 | 100.0 | 100.0 | 100.0 | 96.9 | 24.4 | 1.6 | 1.95 | 1.29 | 3,005 | 6.86 | 1,966 |
| BC | 96.7 | 98.4 | 100.0 | 100.0 | 96.9 | 24.4 | 0.0 | 0.89 | 0.75 | 1,441 | 1.73 | 419 |
| BC + augmentation | 96.7 | 98.4 | 98.0 | 100.0 | 96.9 | 24.1 | 0.0 | 0.89 | 0.76 | 1,429 | 1.71 | 420 |
| BC + DAgger (1) | 96.7 | 98.4 | 100.0 | 100.0 | 96.9 | 24.4 | 0.0 | 0.90 | 0.81 | 1,490 | 1.75 | 424 |
| BC + DAgger (2) | 96.7 | 98.4 | 100.0 | 100.0 | 96.9 | 24.4 | 0.0 | 0.86 | 0.78 | 1,406 | 1.70 | 414 |
| BC + DAgger (3) | 100.0 | 100.0 | 100.0 | 100.0 | 96.9 | 24.4 | 0.0 | 0.87 | 0.75 | 1,398 | 1.70 | 416 |
| BC + aug + DAgger (3) | 100.0 | 100.0 | 100.0 | 100.0 | 96.9 | 24.4 | 0.0 | 0.89 | 0.76 | 1,429 | 1.71 | 420 |
| Oracle (simulates deterministic planners; not an upper bound here) | 100.0 | 100.0 | 100.0 | 100.0 | 96.9 | 24.4 | 0.0 | 0.83 | 0.75 | 1,327 | 1.65 | 405 |

## Clarification behaviour

| System | Recall on infeasible updates | Precision | Timeouts | Budget exhausted |
|---|---|---|---|---|
| Always-Global | 100.0 | 100.0 | 0.0 | 0.0 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 0.0 | 0.0 |
| Static rules | 100.0 | 100.0 | 0.0 | 0.0 |
| LLM coordinator | 100.0 | 100.0 | 0.0 | 0.0 |
| BC | 90.9 | 100.0 | 1.6 | 0.0 |
| BC + augmentation | 100.0 | 100.0 | 1.6 | 0.0 |
| BC + DAgger (1) | 90.9 | 100.0 | 3.2 | 0.0 |
| BC + DAgger (2) | 90.9 | 100.0 | 1.6 | 0.0 |
| BC + DAgger (3) | 100.0 | 100.0 | 0.0 | 0.0 |
| BC + aug + DAgger (3) | 100.0 | 100.0 | 0.0 | 0.0 |
| Oracle (simulates deterministic planners; not an upper bound here) | 100.0 | 100.0 | 0.0 | 0.0 |

## LLM usage per system (first seed for learned systems)

| System | Requests | Billed calls | Cache hits | Errors | Fallbacks | Fallback rate | Degraded |
|---|---|---|---|---|---|---|---|
| Always-Global | 314 | 0 | 314 | 0 | 0 | 0.0% | no |
| Always-Global (deterministic control) | 314 | 0 | 314 | 0 | 0 | 0.0% | no |
| Static rules | 121 | 0 | 121 | 0 | 0 | 0.0% | no |
| LLM coordinator | 432 | 0 | 432 | 0 | 0 | 0.0% | no |
| BC | 109 | 0 | 109 | 0 | 0 | 0.0% | no |
| BC + augmentation | 108 | 0 | 108 | 0 | 0 | 0.0% | no |
| BC + DAgger (1) | 110 | 0 | 110 | 0 | 0 | 0.0% | no |
| BC + DAgger (2) | 107 | 0 | 107 | 0 | 0 | 0.0% | no |
| BC + DAgger (3) | 107 | 0 | 107 | 0 | 0 | 0.0% | no |
| BC + aug + DAgger (3) | 108 | 0 | 108 | 0 | 0 | 0.0% | no |
| Oracle (simulates deterministic planners; not an upper bound here) | 104 | 0 | 104 | 0 | 0 | 0.0% | no |

## By update type

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | add | delete | replace | reprioritize |
|---|---|---|---|---|
| Always-Global | 100.0 / 92 | 100.0 / 69 | 100.0 / 100 | 100.0 / 100 |
| Always-Global (deterministic control) | 100.0 / 92 | 100.0 / 69 | 100.0 / 100 | 100.0 / 100 |
| Static rules | 100.0 / 96 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| LLM coordinator | 100.0 / 96 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC | 97.8 / 96 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + augmentation | 100.0 / 96 | 100.0 / 100 | 90.0 / 100 | 100.0 / 100 |
| BC + DAgger (1) | 97.8 / 96 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + DAgger (2) | 97.8 / 96 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + DAgger (3) | 100.0 / 96 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| BC + aug + DAgger (3) | 100.0 / 96 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |
| Oracle (simulates deterministic planners; not an upper bound here) | 100.0 / 96 | 100.0 / 100 | 100.0 / 100 | 100.0 / 100 |

## By turn position (4th turn only exists in test)

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | turn 1 | turn 2 | turn 3 |
|---|---|---|---|
| Always-Global | 100.0 / 94 | 100.0 / 90 | 100.0 / 91 |
| Always-Global (deterministic control) | 100.0 / 94 | 100.0 / 90 | 100.0 / 91 |
| Static rules | 100.0 / 98 | 100.0 / 97 | 100.0 / 94 |
| LLM coordinator | 100.0 / 98 | 100.0 / 97 | 100.0 / 94 |
| BC | 100.0 / 98 | 100.0 / 97 | 91.7 / 94 |
| BC + augmentation | 100.0 / 98 | 95.2 / 97 | 100.0 / 94 |
| BC + DAgger (1) | 100.0 / 98 | 100.0 / 97 | 91.7 / 94 |
| BC + DAgger (2) | 100.0 / 98 | 100.0 / 97 | 91.7 / 94 |
| BC + DAgger (3) | 100.0 / 98 | 100.0 / 97 | 100.0 / 94 |
| BC + aug + DAgger (3) | 100.0 / 98 | 100.0 / 97 | 100.0 / 94 |
| Oracle (simulates deterministic planners; not an upper bound here) | 100.0 / 98 | 100.0 / 97 | 100.0 / 94 |

## Figures

![pareto](pareto.png)

![error](error_vs_step.png)

![recovery](recovery.png)
