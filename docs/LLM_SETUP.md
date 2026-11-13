# Plugging in an LLM

Without a key everything runs offline with deterministic components. When you set a provider, four things change and nothing else:

| Component | Offline | With an LLM |
|---|---|---|
| Constraint Tracker | Rule-based; only understands the template phrasings | Understands free-form messages; output validated against the schema, rules used as fallback |
| Component agents (transport, accommodation, meals, attractions) | Deterministic best choice | LLM picks from a shortlist; invalid choices fall back to the deterministic one |
| `llm_coordinator` | not available | LLM chooses every coordinator action |
| Cost | Simulated cost model | Measured requests and tokens (shown next to the simulated ones) |

The learned coordinator does not call the LLM at decision time. That's the point of distilling the coordinator into a small model: with an API connected, the agents get smarter while coordination stays cheap. Compare the "Measured LLM requests/turn" column of `llm_coordinator` against the learned systems.

## 1. Configure

```bash
cp .env.example .env      # .env is git-ignored
```

Fill in one provider.

**OpenAI-compatible:** OpenAI, OpenRouter, Together, Groq, a local vLLM server, or Ollama.
```
TASKFLOW_LLM_PROVIDER=openai
TASKFLOW_LLM_MODEL=<model id from your provider>
OPENAI_API_KEY=<key>
# TASKFLOW_LLM_BASE_URL=https://openrouter.ai/api/v1     # for non-OpenAI endpoints
# TASKFLOW_LLM_BASE_URL=http://localhost:11434/v1        # Ollama, no key needed
```

**Anthropic:**
```
TASKFLOW_LLM_PROVIDER=anthropic
TASKFLOW_LLM_MODEL=<model id>
ANTHROPIC_API_KEY=<key>
```

Every script also takes `--llm offline|fake|openai|anthropic`, which overrides `TASKFLOW_LLM_PROVIDER`.

## 2. Check the wiring without spending money

```bash
.venv/bin/python scripts/demo.py --llm fake --policy llm_coordinator
.venv/bin/python -m pytest -q tests/test_llm.py
```

`fake` is a local stand-in that answers every prompt, so every LLM code path runs. Its token counts are word counts.

## 3. Run with the real model

```bash
.venv/bin/python scripts/demo.py --policy llm_coordinator           # LLM coordinator + LLM agents
.venv/bin/python scripts/demo.py --interactive                      # type anything, e.g. "make it cheaper, we're broke"
.venv/bin/python scripts/evaluate.py --llm openai --limit 30 --seeds 0 --skip-recovery
```

- **Where results go:** `results/llm-<provider>/`, so the committed offline results aren't overwritten.
- **Caching:** every request is cached under `cache/llm/` (git-ignored). Re-running the same evaluation costs nothing.

**Rough request counts per turn,** measured with the fake backend on 40 test episodes (real models may differ):

| Coordinator | Requests per turn | What the requests are |
|---|---|---|
| learned | ~1.5 | tracker + component agents |
| static rules | ~2.4 | tracker + component agents |
| `llm_coordinator` | ~6 | adds one request per coordinator step |

Multiply by turns × systems before launching a full run. The test split has 741 turns.

## 4. Train with the LLM teacher (T15)

```bash
.venv/bin/python scripts/train.py --teacher llm --llm openai --seeds 0 --limit 100
.venv/bin/python scripts/evaluate.py --model-suffix _llmteacher --seeds 0
```

Every state the student visits is labeled by the LLM coordinator (one request per state, cached). Models are saved with an `_llmteacher` suffix so they don't replace the oracle-taught models.

## 5. Iterate on prompts

- **Where prompts live:** all in `taskflow/llm/prompts.py`. Each one has a `ROLE:` line and a JSON `INPUT:` block.
- **Reading transcripts:** look at `cache/llm/**/*.json`.
- **When you change a prompt:** if you change its input format, update `taskflow/llm/fake.py` too, so the tests keep passing.
- **Watching fallbacks:** `LLMCoordinator.fallbacks` counts invalid replies. Component agents fall back silently, so add logging if you need to see how often.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `set TASKFLOW_LLM_MODEL ...` | Model id missing in `.env` |
| `HTTP 401` | Wrong key or wrong provider/base URL pair |
| `HTTP 404` | Model id not available at that endpoint |
| `HTTP 429` | Rate limited; the client retries 3 times with backoff. Use `--limit` or a slower tier |
| Tracker shows `(rules)` in the demo | The LLM reply failed validation; the rule parser was used |
| Results identical after a prompt change | Expected only if the request text didn't change (cache key = full request) |
