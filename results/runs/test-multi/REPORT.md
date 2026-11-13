# Results (test_multi split)

Config: `{'seeds': [0, 1, 2], 'split': 'test_multi', 'limit': None, 'skip_recovery': True, 'model_suffix': '', 'call_cap': None, 'llm': 'offline', 'models': '4ec8bf2206a9'}`

git `cf78ea1` (uncommitted changes) · fingerprints `{'source': '76eebacf7b66', 'prompts': 'f9352f57f9ee', 'tasks': '31cf06aeb6b9'}`

Rates are percentages. Learned systems: mean ± std over training seeds. LLM calls/tool calls/est. tokens come from the simulated cost model (see README).

| System | Final pass | Revision success | New constr. sat. | Retention | Legacy unaffected preserved | Slots edited | Unneeded global | LLM calls/turn | Tool calls/turn | Est. tokens/turn |
|---|---|---|---|---|---|---|---|---|---|---|
| Always-Global | 100.0 | 100.0 | 100.0 | 100.0 | 16.5 | 93.3 | 92.0 | 4.08 | 3.00 | 6,024 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 67.9 | 92.0 | 4.08 | 3.00 | 6,024 |
| Static rules | 100.0 | 100.0 | 100.0 | 100.0 | 34.4 | 77.4 | 75.4 | 4.09 | 2.26 | 6,046 |
| Static rules (cost-aware) | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 39.6 | 0.0 | 2.01 | 0.00 | 2,926 |
| BC | 98.8 ± 0.9 | 98.8 ± 0.9 | 98.7 ± 1.0 | 100.0 | 100.0 | 37.6 ± 0.3 | 0.0 | 2.06 ± 0.01 | 0.00 | 2,995 |
| BC + augmentation | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 38.3 ± 0.6 | 0.0 | 2.03 ± 0.01 | 0.00 | 2,951 |
| BC + DAgger (1) | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 38.4 ± 0.3 | 0.0 | 2.03 ± 0.01 | 0.00 | 2,951 |
| BC + DAgger (2) | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 38.0 ± 0.2 | 0.0 | 2.02 ± 0.01 | 0.00 | 2,937 |
| BC + DAgger (3) | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 38.2 ± 0.4 | 0.0 | 2.03 ± 0.00 | 0.00 | 2,944 |
| BC + aug + DAgger (3) | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 38.0 ± 0.2 | 0.0 | 2.02 ± 0.00 | 0.00 | 2,933 |
| Deterministic scripted expert | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 37.7 | 0.0 | 2.01 | 0.00 | 2,926 |

## Minimum necessary changes

Exact minimum slot edits over complete feasible plans. Scored only on successful feasible turns; read alongside revision success and the scored-turn count. Budget turns include all costed slots. Optimal preservation = 1 − excess edits / (13 − minimum edits); undefined when all 13 must change. The legacy unaffected-slot metric above is retained for comparison.

| System | Scored turns (mean) | Minimum edits | Excess edits | Optimal preservation % |
|---|---|---|---|---|
| Always-Global | 127 | 4.12 | 8.01 | 16.0 |
| Always-Global (deterministic control) | 127 | 4.12 | 4.71 | 53.1 |
| Static rules | 127 | 4.12 | 5.94 | 33.2 |
| Static rules (cost-aware) | 127 | 4.12 | 1.03 | 87.2 |
| BC | 125.333 | 4.12 ± 0.00 | 0.79 ± 0.02 | 89.5 ± 0.2 |
| BC + augmentation | 127 | 4.12 | 0.86 ± 0.08 | 88.7 ± 0.7 |
| BC + DAgger (1) | 127 | 4.12 | 0.87 ± 0.04 | 88.6 ± 0.4 |
| BC + DAgger (2) | 127 | 4.12 | 0.82 ± 0.03 | 89.1 ± 0.3 |
| BC + DAgger (3) | 127 | 4.12 | 0.85 ± 0.05 | 88.9 ± 0.5 |
| BC + aug + DAgger (3) | 127 | 4.12 | 0.82 ± 0.03 | 89.1 ± 0.3 |
| Deterministic scripted expert | 127 | 4.12 | 0.78 | 89.5 |

## Clarification behaviour

| System | Recall on infeasible updates | Precision | Timeouts | Budget exhausted |
|---|---|---|---|---|
| Always-Global | 100.0 | 100.0 | 0.0 | 0.0 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 0.0 | 0.0 |
| Static rules | 100.0 | 100.0 | 0.0 | 0.0 |
| Static rules (cost-aware) | 100.0 | 100.0 | 0.0 | 0.0 |
| BC | 100.0 | 100.0 | 1.2 ± 0.9 | 0.0 |
| BC + augmentation | 100.0 | 100.0 | 0.0 | 0.0 |
| BC + DAgger (1) | 100.0 | 100.0 | 0.0 | 0.0 |
| BC + DAgger (2) | 100.0 | 100.0 | 0.0 | 0.0 |
| BC + DAgger (3) | 100.0 | 100.0 | 0.0 | 0.0 |
| BC + aug + DAgger (3) | 100.0 | 100.0 | 0.0 | 0.0 |
| Deterministic scripted expert | 100.0 | 100.0 | 0.0 | 0.0 |

## By difficulty level (multi-component family)

Revision success % / excess edits per turn / global rebuild %. Learned systems: training seed 0.

| System | L0 impossible (ask) | L1 one component | L2 two components | L3 three+ components |
|---|---|---|---|---|
| Always-Global | 100.0 / – / 100 | 100.0 / 11.23 / 100 | 100.0 / 9.15 / 100 | 100.0 / 4.33 / 100 |
| Always-Global (deterministic control) | 100.0 / – / 100 | 100.0 / 7.33 / 100 | 100.0 / 5.57 / 100 | 100.0 / 1.79 / 100 |
| Static rules | 100.0 / – / 0 | 100.0 / 2.50 / 23 | 100.0 / 9.15 / 100 | 100.0 / 4.33 / 100 |
| Static rules (cost-aware) | 100.0 / – / 0 | 100.0 / 0.33 / 0 | 100.0 / 0.81 / 0 | 100.0 / 1.79 / 0 |
| BC | 100.0 / – / 0 | 100.0 / 0.13 / 0 | 100.0 / 0.41 / 0 | 100.0 / 1.79 / 0 |
| BC + augmentation | 100.0 / – / 0 | 100.0 / 0.00 / 0 | 100.0 / 0.41 / 0 | 100.0 / 1.79 / 0 |
| BC + DAgger (1) | 100.0 / – / 0 | 100.0 / 0.13 / 0 | 100.0 / 0.41 / 0 | 100.0 / 1.79 / 0 |
| BC + DAgger (2) | 100.0 / – / 0 | 100.0 / 0.13 / 0 | 100.0 / 0.41 / 0 | 100.0 / 1.79 / 0 |
| BC + DAgger (3) | 100.0 / – / 0 | 100.0 / 0.00 / 0 | 100.0 / 0.41 / 0 | 100.0 / 1.79 / 0 |
| BC + aug + DAgger (3) | 100.0 / – / 0 | 100.0 / 0.13 / 0 | 100.0 / 0.41 / 0 | 100.0 / 1.79 / 0 |
| Deterministic scripted expert | 100.0 / – / 0 | 100.0 / 0.00 / 0 | 100.0 / 0.41 / 0 | 100.0 / 1.79 / 0 |

## By update type

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | replace |
|---|---|
| Always-Global | 100.0 / 17 |
| Always-Global (deterministic control) | 100.0 / 100 |
| Static rules | 100.0 / 34 |
| Static rules (cost-aware) | 100.0 / 100 |
| BC | 100.0 / 100 |
| BC + augmentation | 100.0 / 100 |
| BC + DAgger (1) | 100.0 / 100 |
| BC + DAgger (2) | 100.0 / 100 |
| BC + DAgger (3) | 100.0 / 100 |
| BC + aug + DAgger (3) | 100.0 / 100 |
| Deterministic scripted expert | 100.0 / 100 |

## By turn position (4th turn only exists in test)

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | turn 1 |
|---|---|
| Always-Global | 100.0 / 17 |
| Always-Global (deterministic control) | 100.0 / 100 |
| Static rules | 100.0 / 34 |
| Static rules (cost-aware) | 100.0 / 100 |
| BC | 100.0 / 100 |
| BC + augmentation | 100.0 / 100 |
| BC + DAgger (1) | 100.0 / 100 |
| BC + DAgger (2) | 100.0 / 100 |
| BC + DAgger (3) | 100.0 / 100 |
| BC + aug + DAgger (3) | 100.0 / 100 |
| Deterministic scripted expert | 100.0 / 100 |

## Figures

![pareto](pareto.png)

![error](error_vs_step.png)

![recovery](recovery.png)
