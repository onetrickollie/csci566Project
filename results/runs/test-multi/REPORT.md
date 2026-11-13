# Results (test_multi split)

Config: `{'seeds': [0, 1, 2], 'split': 'test_multi', 'limit': None, 'skip_recovery': True, 'model_suffix': '', 'call_cap': None, 'llm': 'offline', 'models': '3e2281036607'}`

git `36d3395` · fingerprints `{'source': '09a45a79ca24', 'prompts': 'f9352f57f9ee', 'tasks': 'c6a92573e38a'}`

Rates are percentages. Learned systems: mean ± std over training seeds. LLM calls/tool calls/est. tokens come from the simulated cost model (see README).

| System | Final pass | Revision success | New constr. sat. | Retention | Legacy unaffected preserved | Slots edited | Unneeded global | LLM calls/turn | Tool calls/turn | Est. tokens/turn |
|---|---|---|---|---|---|---|---|---|---|---|
| Always-Global | 100.0 | 100.0 | 100.0 | 100.0 | 6.9 | 96.1 | 79.7 | 4.00 | 3.00 | 6,000 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 67.8 | 79.7 | 4.00 | 3.00 | 6,000 |
| Static rules | 100.0 | 100.0 | 100.0 | 100.0 | 37.3 | 67.4 | 47.1 | 3.70 | 2.02 | 5,543 |
| BC | 100.0 | 100.0 | 100.0 | 100.0 | 79.6 ± 4.4 | 37.2 ± 1.9 | 4.3 ± 2.6 | 2.11 ± 0.06 | 0.67 ± 0.15 | 3,167 |
| BC + augmentation | 100.0 | 100.0 | 100.0 | 100.0 | 79.2 | 36.9 ± 0.1 | 2.9 ± 0.6 | 2.09 ± 0.02 | 0.70 ± 0.02 | 3,141 |
| BC + DAgger (1) | 100.0 | 100.0 | 100.0 | 100.0 | 77.1 ± 1.0 | 38.5 ± 0.8 | 5.3 ± 1.5 | 2.12 ± 0.03 | 0.77 ± 0.04 | 3,178 |
| BC + DAgger (2) | 100.0 | 100.0 | 100.0 | 100.0 | 79.6 ± 1.8 | 36.8 ± 1.3 | 1.7 ± 1.5 | 2.04 ± 0.04 | 0.64 ± 0.06 | 3,058 |
| BC + DAgger (3) | 100.0 | 100.0 | 100.0 | 100.0 | 78.9 ± 0.7 | 37.2 ± 0.7 | 1.9 ± 0.9 | 2.04 ± 0.02 | 0.67 ± 0.03 | 3,054 |
| BC + aug + DAgger (3) | 100.0 | 100.0 | 100.0 | 100.0 | 78.9 ± 1.2 | 36.8 ± 0.9 | 2.9 ± 2.4 | 2.06 ± 0.05 | 0.70 ± 0.07 | 3,083 |
| Deterministic scripted expert | 100.0 | 100.0 | 100.0 | 100.0 | 80.6 | 35.6 | 0.0 | 1.99 | 0.61 | 2,989 |

## Minimum necessary changes

Exact minimum slot edits over complete feasible plans. Scored only on successful feasible turns; read alongside revision success and the scored-turn count. Budget turns include all costed slots. Optimal preservation = 1 − excess edits / (13 − minimum edits); undefined when all 13 must change. The legacy unaffected-slot metric above is retained for comparison.

| System | Scored turns (mean) | Minimum edits | Excess edits | Optimal preservation % |
|---|---|---|---|---|
| Always-Global | 138 | 2.88 | 9.62 | 6.4 |
| Always-Global (deterministic control) | 138 | 2.88 | 5.94 | 44.1 |
| Static rules | 138 | 2.88 | 5.88 | 37.5 |
| BC | 138 | 2.88 | 1.96 ± 0.25 | 75.1 ± 2.6 |
| BC + augmentation | 138 | 2.88 | 1.92 ± 0.01 | 75.6 ± 0.2 |
| BC + DAgger (1) | 138 | 2.88 | 2.13 ± 0.10 | 73.5 ± 1.0 |
| BC + DAgger (2) | 138 | 2.88 | 1.91 ± 0.16 | 75.8 ± 1.6 |
| BC + DAgger (3) | 138 | 2.88 | 1.96 ± 0.09 | 75.3 ± 0.9 |
| BC + aug + DAgger (3) | 138 | 2.88 | 1.91 ± 0.12 | 75.7 ± 1.2 |
| Deterministic scripted expert | 138 | 2.88 | 1.75 | 77.4 |

## Clarification behaviour

| System | Recall on infeasible updates | Precision | Timeouts | Budget exhausted |
|---|---|---|---|---|
| Always-Global | – | – | 0.0 | 0.0 |
| Always-Global (deterministic control) | – | – | 0.0 | 0.0 |
| Static rules | – | – | 0.0 | 0.0 |
| BC | – | – | 0.0 | 0.0 |
| BC + augmentation | – | – | 0.0 | 0.0 |
| BC + DAgger (1) | – | – | 0.0 | 0.0 |
| BC + DAgger (2) | – | – | 0.0 | 0.0 |
| BC + DAgger (3) | – | – | 0.0 | 0.0 |
| BC + aug + DAgger (3) | – | – | 0.0 | 0.0 |
| Deterministic scripted expert | – | – | 0.0 | 0.0 |

## By update type

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | replace |
|---|---|
| Always-Global | 100.0 / 7 |
| Always-Global (deterministic control) | 100.0 / 100 |
| Static rules | 100.0 / 37 |
| BC | 100.0 / 86 |
| BC + augmentation | 100.0 / 79 |
| BC + DAgger (1) | 100.0 / 76 |
| BC + DAgger (2) | 100.0 / 78 |
| BC + DAgger (3) | 100.0 / 78 |
| BC + aug + DAgger (3) | 100.0 / 78 |
| Deterministic scripted expert | 100.0 / 81 |

## By turn position (4th turn only exists in test)

Revision success % / unaffected preserved %. Learned systems: training seed 0.

| System | turn 1 |
|---|---|
| Always-Global | 100.0 / 7 |
| Always-Global (deterministic control) | 100.0 / 100 |
| Static rules | 100.0 / 37 |
| BC | 100.0 / 86 |
| BC + augmentation | 100.0 / 79 |
| BC + DAgger (1) | 100.0 / 76 |
| BC + DAgger (2) | 100.0 / 78 |
| BC + DAgger (3) | 100.0 / 78 |
| BC + aug + DAgger (3) | 100.0 / 78 |
| Deterministic scripted expert | 100.0 / 81 |

## Figures

![pareto](pareto.png)

![error](error_vs_step.png)

![recovery](recovery.png)
