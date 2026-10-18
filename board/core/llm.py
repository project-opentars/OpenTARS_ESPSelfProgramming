# Modelo no formato "OpenAI chat completions": serve para Gemini, OpenAI, Groq, OpenRouter, LM Studio e Ollama (/v1).
import json
from . import http_client

PRESETS = {
    "ollama": {"base_url": "http://192.168.0.10:11434/v1", "model": "qwen3:4b", "needs_key": False},
    "lmstudio": {"base_url": "http://192.168.0.10:1234/v1", "model": "", "needs_key": False},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-flash-latest", "needs_key": True},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini", "needs_key": True},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-20b", "needs_key": True},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-oss-20b:free", "needs_key": True},
    "custom": {"base_url": "", "model": "", "needs_key": False},
}


class LLMError(Exception):
    pass


def _headers(cfg):
    h = {"Content-Type": "application/json"}
    if cfg.get("llm_api_key"):
        h["Authorization"] = "Bearer " + cfg["llm_api_key"]
    return h


def clean_messages(messages, base_url):
    """Só os campos do padrão: provedores estritos (Groq) recusam campos extras. O Gemini precisa receber de volta
    o extra_content (thought_signature) das chamadas de ferramenta, então ele fica quando o destino é o Gemini."""
    keep_extra = "googleapis" in base_url
    out = []
    for m in messages:
        c = {"role": m["role"], "content": m.get("content")}
        if m["role"] == "tool":
            c["tool_call_id"] = m.get("tool_call_id", "")
            if c["content"] is None:
                c["content"] = ""
        if m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                t = {"id": tc.get("id", ""), "type": "function",
                     "function": {"name": tc["function"]["name"], "arguments": tc["function"].get("arguments") or "{}"}}
                if keep_extra and tc.get("extra_content"):
                    t["extra_content"] = tc["extra_content"]
                calls.append(t)
            c["tool_calls"] = calls
        out.append(c)
    return out


async def chat(cfg, messages, tools=None):
    base = cfg["llm_base_url"].rstrip("/")
    if not base:
        raise LLMError("no model configured: open Settings and choose a provider")
    body = {"model": cfg["llm_model"], "messages": clean_messages(messages, base), "max_tokens": cfg.get("llm_max_tokens", 4096)}
    if tools:
        body["tools"] = tools
    status, _, data = await http_client.request("POST", base + "/chat/completions", _headers(cfg), json.dumps(body),
                                                cfg.get("llm_timeout_s", 120))
    if status != 200:
        raise LLMError("HTTP %d: %s" % (status, data[:400].decode("utf-8", "replace") if data else ""))
    try:
        resp = json.loads(data)
        msg = resp["choices"][0]["message"]
    except (ValueError, KeyError, IndexError):
        raise LLMError("unexpected reply: " + data[:300].decode("utf-8", "replace"))
    msg["role"] = "assistant"
    return msg


async def list_models(cfg):
    base = cfg["llm_base_url"].rstrip("/")
    status, _, data = await http_client.request("GET", base + "/models", _headers(cfg), None, 20)
    if status != 200:
        raise LLMError("HTTP %d: %s" % (status, data[:200].decode("utf-8", "replace") if data else ""))
    items = json.loads(data).get("data", [])
    ids = [str(m.get("id", "")) for m in items]
    return sorted([i[7:] if i.startswith("models/") else i for i in ids if i])
