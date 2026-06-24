import json
import logging
import os
import re
import threading
import time
from typing import Any

import httpx
from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

_token_counter: int = 0
_token_lock = threading.Lock()


def reset_token_count() -> None:
    global _token_counter
    with _token_lock:
        _token_counter = 0


def get_token_count() -> int:
    with _token_lock:
        return _token_counter


def _add_tokens(n: int) -> None:
    if n:
        with _token_lock:
            global _token_counter
            _token_counter += n


# ── Local Ollama config ────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OPENAI_BASE: str = f"{OLLAMA_BASE_URL}/v1"
TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "900"))
MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "5"))

# ── Cloud / Multi-model config ─────────────────────────────────────────────────
CLOUD_BASE_URL: str = os.getenv(
    "CLOUD_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
)
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
CLOUD_MODEL: str = os.getenv("CLOUD_MODEL", "gemma-4-31b-it")

# ── OpenRouter / Anthropic ─────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "https://openrouter.ai/api/v1")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "anthropic/claude-3.5-sonnet")

MODEL_PRESETS: dict[str, str] = {
    "local": os.getenv("MODEL_LOCAL", "gemma4:12b"),
    "cloud": CLOUD_MODEL,
    "anthropic": ANTHROPIC_MODEL,
}

CONTEXT_SETUP: dict[str, str] = {
    "local": os.getenv(
        "CONTEXT_LOCAL",
        "You are an expert software architect powered by Gemma 4 12B. Produce comprehensive, well-documented code.",
    ),
    "cloud": "You are an expert software architect powered by Gemma 4 31B. Produce comprehensive, well-documented, production-ready Python code.",
    "anthropic": "You are an expert software architect powered by Claude 3.5 Sonnet. Produce comprehensive, well-documented, production-ready Python code.",
}

_pull_status: dict[str, str] = {}
_pull_lock = threading.Lock()

_openai_client: OpenAI | None = None
_client_lock = threading.Lock()

_cloud_client: OpenAI | None = None
_cloud_lock = threading.Lock()

_anthropic_client: OpenAI | None = None
_anthropic_lock = threading.Lock()


def _client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        with _client_lock:
            if _openai_client is None:
                _openai_client = OpenAI(base_url=_OPENAI_BASE, api_key="ollama")
    return _openai_client


def _cloud() -> OpenAI:
    global _cloud_client
    if _cloud_client is None:
        with _cloud_lock:
            if _cloud_client is None:
                if not GOOGLE_API_KEY:
                    raise RuntimeError(
                        "GOOGLE_API_KEY is not set. "
                        "Get a free key at https://ai.google.dev/ "
                        "then add GOOGLE_API_KEY=... to your .env file."
                    )
                _cloud_client = OpenAI(base_url=CLOUD_BASE_URL, api_key=GOOGLE_API_KEY)
    return _cloud_client


def _anthropic() -> OpenAI:
    global _anthropic_client
    if _anthropic_client is None:
        with _anthropic_lock:
            if _anthropic_client is None:
                if not ANTHROPIC_API_KEY:
                    raise RuntimeError(
                        "ANTHROPIC_API_KEY is not set. "
                        "Get a key at https://openrouter.ai/keys "
                        "then add ANTHROPIC_API_KEY=... to your .env file."
                    )
                _anthropic_client = OpenAI(base_url=ANTHROPIC_BASE_URL, api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


_CLOUD_PRESETS = {"cloud", "anthropic"}


def is_cloud_preset(preset: str) -> bool:
    return preset.lower() in _CLOUD_PRESETS


def is_cloud_available() -> bool:
    return bool(GOOGLE_API_KEY.strip() or ANTHROPIC_API_KEY.strip())


# ── Google AI Diagnostics ───────────────────────────────────────────────────

GOOGLE_CREDENTIAL_DIAGNOSTICS: dict[str, Any] = {
    "api_key_configured": False,
    "api_key_format_valid": False,
    "api_key_prefix": "",
    "base_url_configured": False,
    "last_diagnostic_error": "",
    "diagnostic_timestamp": 0,
}


def diagnose_google_credentials() -> dict[str, Any]:
    """Run diagnostics on Google AI credentials. Returns diagnostic results."""
    now = time.time()
    diag = {
        "api_key_configured": bool(GOOGLE_API_KEY.strip()),
        "api_key_format_valid": False,
        "api_key_prefix": GOOGLE_API_KEY[:8] + "..." if len(GOOGLE_API_KEY) > 8 else "",
        "base_url": CLOUD_BASE_URL,
        "base_url_configured": bool(CLOUD_BASE_URL.strip()),
        "model": CLOUD_MODEL,
        "errors": [],
        "can_authenticate": False,
    }

    # Check API key format
    if GOOGLE_API_KEY:
        if GOOGLE_API_KEY.startswith("AIza"):
            diag["api_key_format_valid"] = True
        elif GOOGLE_API_KEY.startswith("sk-"):
            # OpenRouter style key
            diag["api_key_format_valid"] = True
        elif len(GOOGLE_API_KEY) > 20:
            diag["api_key_format_valid"] = True
        else:
            diag["errors"].append("API key too short or invalid format")

    # Try a lightweight auth test
    if diag["api_key_format_valid"] and diag["base_url_configured"]:
        try:
            client = OpenAI(base_url=CLOUD_BASE_URL, api_key=GOOGLE_API_KEY, timeout=httpx.Timeout(10))
            # List models as a lightweight auth check
            response = client.models.list()
            diag["can_authenticate"] = True
            available_models = [m.id for m in response.data]
            diag["available_models"] = available_models[:10]
            diag["model_available"] = CLOUD_MODEL in available_models
        except Exception as exc:
            error_str = str(exc)
            diag["errors"].append(error_str[:200])
            if "401" in error_str or "UNAUTHENTICATED" in error_str:
                diag["errors"].append("Authentication failed (401). API key may be invalid or expired.")
            elif "ACCESS_TOKEN_TYPE_UNSUPPORTED" in error_str:
                diag["errors"].append(
                    "ACCESS_TOKEN_TYPE_UNSUPPORTED — the Google AI base URL may be incorrect. "
                    "Expected: https://generativelanguage.googleapis.com/v1beta/openai/"
                )
            elif "403" in error_str:
                diag["errors"].append("Forbidden (403). API key may lack permissions or quota exhausted.")
            elif "404" in error_str:
                diag["errors"].append("Not found (404). Check CLOUD_BASE_URL and model name.")

    # Update global diagnostics cache
    global GOOGLE_CREDENTIAL_DIAGNOSTICS
    GOOGLE_CREDENTIAL_DIAGNOSTICS.update(
        {
            "api_key_configured": diag["api_key_configured"],
            "api_key_format_valid": diag["api_key_format_valid"],
            "api_key_prefix": diag["api_key_prefix"],
            "base_url_configured": diag["base_url_configured"],
            "last_diagnostic_error": diag["errors"][-1] if diag["errors"] else "",
            "diagnostic_timestamp": now,
        }
    )

    return diag


def get_cloud_health() -> dict[str, Any]:
    """Get comprehensive health status for all cloud providers."""
    google_diag = diagnose_google_credentials()
    anthropic_ok = bool(ANTHROPIC_API_KEY.strip())

    return {
        "google": {
            "configured": google_diag["api_key_configured"],
            "authenticated": google_diag["can_authenticate"],
            "model": CLOUD_MODEL,
            "model_available": google_diag.get("model_available", False),
            "errors": google_diag["errors"],
        },
        "anthropic": {
            "configured": anthropic_ok,
            "model": ANTHROPIC_MODEL,
        },
        "overall": google_diag["can_authenticate"] or anthropic_ok,
        "timestamp": time.time(),
    }


def is_available() -> bool:
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def get_available_models() -> list[str]:
    try:
        data = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5).json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def get_pull_status() -> dict[str, str]:
    with _pull_lock:
        return dict(_pull_status)


def _model_present(model: str) -> bool:
    return any(model == m or model in m for m in get_available_models())


def pull_model(model: str) -> bool:
    with _pull_lock:
        _pull_status[model] = "pulling"
    try:
        logger.info("Pulling Ollama model: %s", model)
        with httpx.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/pull",
            json={"name": model},
            timeout=900,
        ) as stream:
            for raw in stream.iter_lines():
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    if "error" in data:
                        raise RuntimeError(data["error"])
                    if data.get("total"):
                        pct = int(data.get("completed", 0) / data["total"] * 100)
                        logger.debug("  %s — %s %d%%", model, data.get("status", ""), pct)
                except json.JSONDecodeError:
                    pass
        with _pull_lock:
            _pull_status[model] = "ready"
        logger.info("Model ready: %s", model)
        return True
    except Exception as exc:
        logger.error("Failed to pull %s: %s", model, exc)
        with _pull_lock:
            _pull_status[model] = "failed"
        return False


def ensure_models() -> None:
    needed = {MODEL_PRESETS["local"]}
    for model in needed:
        with _pull_lock:
            _pull_status.setdefault(model, "pending")
        try:
            if _model_present(model):
                with _pull_lock:
                    _pull_status[model] = "ready"
                logger.info("Model already present: %s", model)
            else:
                pull_model(model)
        except Exception as exc:
            logger.warning("Could not pull %s (non-fatal): %s", model, exc)
            with _pull_lock:
                _pull_status[model] = "unavailable"


def resolve_model(preset_or_name: str) -> str:
    return MODEL_PRESETS.get(preset_or_name.lower(), preset_or_name)


def get_context(preset_or_name: str) -> str:
    return CONTEXT_SETUP.get(preset_or_name.lower(), "")


def call_model(
    prompt: str,
    system_prompt: str = "You are an expert software engineer.",
    model: str | None = None,
    context_setup: str | None = None,
    job_id: str | None = None,
    agent: str | None = None,
    **kwargs: Any,
) -> str:
    preset = (model or "local").lower()
    model_name = resolve_model(preset)
    ctx = context_setup or get_context(preset)
    full_sys = f"{system_prompt}\n\n{ctx}".strip() if ctx else system_prompt

    if preset == "cloud":
        return _call_cloud(prompt, model_name, full_sys, job_id, agent)
    elif preset == "anthropic":
        return _call_anthropic(prompt, model_name, full_sys, job_id, agent)
    else:
        return _call_local(prompt, model_name, full_sys, job_id, agent)


def _call_local(
    prompt: str,
    model_name: str,
    system_prompt: str,
    job_id: str | None = None,
    agent: str | None = None,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.monotonic()
        try:
            resp = _client().chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.2,
                max_tokens=8192,
                timeout=TIMEOUT,
            )
            text = (resp.choices[0].message.content or "").strip()
            text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL).strip()
            if not text:
                raise ValueError("Model returned an empty response.")
            duration_ms = int((time.monotonic() - t0) * 1000)
            tokens = resp.usage.total_tokens if resp.usage else None
            _add_tokens(tokens)
            _log_structured(
                "INFO",
                "llm_call_ok",
                model=model_name,
                tokens=tokens,
                duration_ms=duration_ms,
                attempt=attempt,
                provider="local",
                job_id=job_id,
                agent=agent,
            )
            return text
        except (APIConnectionError, APITimeoutError) as exc:
            last_exc = exc
            duration_ms = int((time.monotonic() - t0) * 1000)
            _log_structured(
                "WARNING",
                "llm_call_retry",
                model=model_name,
                duration_ms=duration_ms,
                attempt=attempt,
                error=str(exc),
                provider="local",
                job_id=job_id,
                agent=agent,
            )
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        except Exception as exc:
            raise RuntimeError(f"LLM call failed: {exc}") from exc
    raise RuntimeError(f"Ollama failed after {MAX_RETRIES} attempts: {last_exc}")


def _call_cloud(
    prompt: str,
    model_name: str,
    system_prompt: str,
    job_id: str | None = None,
    agent: str | None = None,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.monotonic()
        try:
            resp = _cloud().chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.2,
                max_tokens=8192,
                timeout=TIMEOUT,
            )
            text = (resp.choices[0].message.content or "").strip()
            text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL).strip()
            if not text:
                raise ValueError("Cloud model returned an empty response.")
            duration_ms = int((time.monotonic() - t0) * 1000)
            tokens = resp.usage.total_tokens if resp.usage else None
            _add_tokens(tokens)
            _log_structured(
                "INFO",
                "llm_call_ok",
                model=model_name,
                tokens=tokens,
                duration_ms=duration_ms,
                attempt=attempt,
                provider="cloud_google",
                job_id=job_id,
                agent=agent,
            )
            return text
        except (APIConnectionError, APITimeoutError) as exc:
            last_exc = exc
            duration_ms = int((time.monotonic() - t0) * 1000)
            _log_structured(
                "WARNING",
                "llm_call_retry",
                model=model_name,
                duration_ms=duration_ms,
                attempt=attempt,
                error=str(exc),
                provider="cloud_google",
                job_id=job_id,
                agent=agent,
            )
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        except Exception as exc:
            error_str = str(exc)
            # Auth errors — fall back to local model
            if any(
                kw in error_str
                for kw in (
                    "401",
                    "UNAUTHENTICATED",
                    "ACCESS_TOKEN_TYPE_UNSUPPORTED",
                    "403",
                    "authentication",
                    "api key",
                    "unauthorized",
                )
            ):
                diagnose_google_credentials()
                logger.error("Cloud auth error, falling back to local: %s", error_str[:200])
                return _call_local(prompt, resolve_model("local"), system_prompt, job_id, agent)
            raise RuntimeError(f"Cloud LLM call failed: {exc}") from exc
    raise RuntimeError(f"Cloud (Gemma 4 31B) failed after {MAX_RETRIES} attempts: {last_exc}")


def _call_anthropic(
    prompt: str,
    model_name: str,
    system_prompt: str,
    job_id: str | None = None,
    agent: str | None = None,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.monotonic()
        try:
            resp = _anthropic().chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.2,
                max_tokens=8192,
                timeout=TIMEOUT,
            )
            text = (resp.choices[0].message.content or "").strip()
            text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL).strip()
            if not text:
                raise ValueError("Anthropic model returned an empty response.")
            duration_ms = int((time.monotonic() - t0) * 1000)
            tokens = resp.usage.total_tokens if resp.usage else None
            _add_tokens(tokens)
            _log_structured(
                "INFO",
                "llm_call_ok",
                model=model_name,
                tokens=tokens,
                duration_ms=duration_ms,
                attempt=attempt,
                provider="anthropic_openrouter",
                job_id=job_id,
                agent=agent,
            )
            return text
        except (APIConnectionError, APITimeoutError) as exc:
            last_exc = exc
            duration_ms = int((time.monotonic() - t0) * 1000)
            _log_structured(
                "WARNING",
                "llm_call_retry",
                model=model_name,
                duration_ms=duration_ms,
                attempt=attempt,
                error=str(exc),
                provider="anthropic_openrouter",
                job_id=job_id,
                agent=agent,
            )
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        except Exception as exc:
            error_str = str(exc)
            if any(
                kw in error_str for kw in ("401", "UNAUTHENTICATED", "403", "authentication", "api key", "unauthorized")
            ):
                logger.error("Anthropic auth error, falling back to local: %s", error_str[:200])
                return _call_local(prompt, resolve_model("local"), system_prompt, job_id, agent)
            raise RuntimeError(f"Anthropic LLM call failed: {exc}") from exc
    raise RuntimeError(f"Anthropic (Claude 3.5 Sonnet via OpenRouter) failed after {MAX_RETRIES} attempts: {last_exc}")


def get_available_providers() -> list[dict[str, bool]]:
    return [
        {"name": "local", "available": is_available()},
        {"name": "cloud", "available": bool(GOOGLE_API_KEY.strip())},
        {"name": "anthropic", "available": bool(ANTHROPIC_API_KEY.strip())},
    ]


def _log_structured(level: str, event: str, **kwargs) -> None:
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **kwargs}
    getattr(logger, level.lower(), logger.info)(json.dumps(record))


def clean_code_response(text: str) -> str:
    text = text.strip()
    lines = text.splitlines()
    # Strip leading fences (e.g. ```python, ```py, ```)
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    # Strip trailing fences
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    # If multiple code blocks separated by text, take the longest one
    cleaned = "\n".join(lines).strip()
    if "```" in cleaned:
        blocks = re.split(r"```[\w]*\n?", cleaned)
        cleaned = max((b.strip() for b in blocks if b.strip()), key=len)
    return cleaned.strip()
