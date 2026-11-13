"""Single entry point for every LLM call.

Configuration comes from environment variables (or a local ``.env`` file,
see ``.env.example``):

    TASKFLOW_LLM_PROVIDER   offline (default) | openai | anthropic | fake
    TASKFLOW_LLM_MODEL      model id from your provider (required for openai/anthropic)
    TASKFLOW_LLM_BASE_URL   optional; any OpenAI-compatible endpoint works
                            (OpenAI, OpenRouter, Together, vLLM, Ollama, ...)
    OPENAI_API_KEY / ANTHROPIC_API_KEY
    TASKFLOW_LLM_TEMPERATURE  default 0

Every call is cached on disk (``cache/llm``) by a hash of the request, so
re-running an experiment costs nothing. Usage (calls, tokens, cache hits) is
counted on the client so the environment can record measured cost.

``offline`` means no client at all: callers fall back to the deterministic
components. ``fake`` is a local stand-in used by the tests and by
``--llm fake`` in the demo to exercise every LLM code path without a key.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "cache" / "llm"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Usage:
    """``requests``/``tokens`` count every logical call (cached or not), so
    measured cost does not drop to zero on a re-run; ``calls`` and
    ``cache_hits`` split them into billed and free."""

    requests: int = 0          # logical requests (cached or not)
    calls: int = 0             # successful network calls (billed)
    cache_hits: int = 0
    input_tokens: int = 0      # logical tokens, cached replays included
    output_tokens: int = 0
    billed_input_tokens: int = 0
    billed_output_tokens: int = 0
    errors: int = 0            # failed attempts (after retries)
    seconds: float = 0.0
    fallbacks: dict = field(default_factory=dict)   # component -> count
    fallback_reasons: dict = field(default_factory=dict)  # "component: reason" -> count

    @property
    def degraded(self) -> bool:
        """True if any request failed or any component fell back to rules."""
        return self.errors > 0 or sum(self.fallbacks.values()) > 0

    def as_dict(self) -> dict:
        d = {k: v for k, v in vars(self).items()}
        d["tokens"] = self.tokens
        d["degraded"] = self.degraded
        return d

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def snapshot(self) -> tuple[int, int]:
        return self.requests, self.tokens


class LLMError(RuntimeError):
    """Recoverable failure (rate limit after retries, timeout, malformed reply)."""


class LLMFatalError(LLMError):
    """Configuration/authentication failure. Never hidden by fallbacks."""


def note_fallback(client, component: str, reason: str) -> None:
    """Record that ``component`` used its deterministic fallback."""
    usage = getattr(client, "usage", None)
    if usage is None or not hasattr(usage, "fallbacks"):
        return
    usage.fallbacks[component] = usage.fallbacks.get(component, 0) + 1
    key = f"{component}: {reason[:80]}"
    usage.fallback_reasons[key] = usage.fallback_reasons.get(key, 0) + 1


DEFAULT_ENDPOINT = {"openai": "https://api.openai.com/v1", "anthropic": "https://api.anthropic.com",
                    "fake": "local://fake"}


@dataclass
class LLMClient:
    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.0
    use_cache: bool = True
    timeout: float = 60.0
    usage: Usage = field(default_factory=Usage)

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    @property
    def endpoint(self) -> str:
        """Normalized effective endpoint (part of the cache identity, never the key)."""
        return (self.base_url or DEFAULT_ENDPOINT.get(self.provider, "")).rstrip("/").lower()

    def identity(self) -> dict:
        return {"provider": self.provider, "model": self.model, "endpoint": self.endpoint,
                "temperature": self.temperature}

    # ------------------------------------------------------------------
    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        key = hashlib.sha256(json.dumps(
            [self.provider, self.endpoint, self.model, self.temperature, system, user,
             max_tokens]).encode()).hexdigest()
        path = CACHE_DIR / key[:2] / f"{key}.json"
        self.usage.requests += 1
        if self.use_cache and path.exists():
            rec = json.loads(path.read_text())
            self.usage.cache_hits += 1
            self.usage.input_tokens += rec.get("input_tokens", 0)
            self.usage.output_tokens += rec.get("output_tokens", 0)
            return rec["text"]
        t0 = time.time()
        try:
            text, tin, tout = self._call(system, user, max_tokens)
        except Exception:
            self.usage.errors += 1
            raise
        self.usage.seconds += time.time() - t0
        self.usage.calls += 1
        self.usage.input_tokens += tin
        self.usage.output_tokens += tout
        self.usage.billed_input_tokens += tin
        self.usage.billed_output_tokens += tout
        if self.use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"text": text, "input_tokens": tin, "output_tokens": tout,
                                        "model": self.label, "endpoint": self.endpoint}))
        return text

    def complete_json(self, system: str, user: str, max_tokens: int = 600) -> dict:
        return extract_json(self.complete(system, user, max_tokens))

    # ------------------------------------------------------------------
    def _call(self, system: str, user: str, max_tokens: int) -> tuple[str, int, int]:
        if self.provider == "fake":
            from taskflow.llm.fake import respond

            text = respond(system, user)
            return text, len((system + user).split()), len(text.split())
        if self.provider == "openai":
            url = (self.base_url or DEFAULT_ENDPOINT["openai"]).rstrip("/") + "/chat/completions"
            body = {"model": self.model, "temperature": self.temperature, "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}]}
            data = _post(url, body, {"Authorization": f"Bearer {self.api_key}"}, self.timeout)
            u = data.get("usage", {})
            return (data["choices"][0]["message"]["content"], u.get("prompt_tokens", 0),
                    u.get("completion_tokens", 0))
        if self.provider == "anthropic":
            url = (self.base_url or DEFAULT_ENDPOINT["anthropic"]).rstrip("/") + "/v1/messages"
            body = {"model": self.model, "temperature": self.temperature, "max_tokens": max_tokens,
                    "system": system, "messages": [{"role": "user", "content": user}]}
            data = _post(url, body, {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                         self.timeout)
            u = data.get("usage", {})
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            return text, u.get("input_tokens", 0), u.get("output_tokens", 0)
        raise LLMFatalError(f"unknown provider {self.provider!r}")


def _post(url: str, body: dict, headers: dict, timeout: float, retries: int = 3) -> dict:
    req_headers = {"Content-Type": "application/json", **headers}
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code in (400, 401, 403, 404):
                # Bad key, bad model id, bad endpoint: retrying or falling back would hide it.
                raise LLMFatalError(f"HTTP {e.code} from {url}: {msg}") from None
            last = LLMError(f"HTTP {e.code} from {url}: {msg}")
            if e.code not in (429, 500, 502, 503, 529):
                break
        except (urllib.error.URLError, TimeoutError) as e:
            last = LLMError(f"request to {url} failed: {e}")
        time.sleep(2 ** attempt)
    raise last  # type: ignore[misc]


def extract_json(text: str) -> dict:
    """Parse the first JSON object in a model reply (tolerates code fences and prose)."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise LLMError(f"no JSON object in reply: {text[:200]!r}")
    return json.loads(m.group(0))


def get_client(provider: str | None = None) -> LLMClient | None:
    """Build the configured client, or None for offline mode."""
    load_dotenv()
    provider = (provider or os.environ.get("TASKFLOW_LLM_PROVIDER") or "offline").lower()
    if provider in ("", "offline", "none"):
        return None
    temp = float(os.environ.get("TASKFLOW_LLM_TEMPERATURE", "0"))
    if provider == "fake":
        return LLMClient("fake", "fake", temperature=temp)
    model = os.environ.get("TASKFLOW_LLM_MODEL", "")
    if not model:
        raise LLMFatalError("set TASKFLOW_LLM_MODEL to a model id from your provider")
    key_var = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider)
    if key_var is None:
        raise LLMFatalError(f"unknown TASKFLOW_LLM_PROVIDER={provider!r}")
    key = os.environ.get(key_var, "")
    if not key and not os.environ.get("TASKFLOW_LLM_BASE_URL"):
        raise LLMFatalError(f"set {key_var} (or TASKFLOW_LLM_BASE_URL for a local server)")
    return LLMClient(provider, model, api_key=key, base_url=os.environ.get("TASKFLOW_LLM_BASE_URL", ""),
                     temperature=temp)
