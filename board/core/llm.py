# Modelo no formato "OpenAI chat completions": serve para Gemini, OpenAI, Groq, OpenRouter, LM Studio e Ollama (/v1).
import json
from . import http_client

PRESETS = {   # ollama e lmstudio: o endereço é o IP do computador da pessoa, que eu não sei: a página deixa o campo vazio com um exemplo
    "ollama": {"base_url": "", "example": "http://192.168.1.20:11434/v1", "model": "qwen3:4b", "needs_key": False},
    "lmstudio": {"base_url": "", "example": "http://192.168.1.20:1234/v1", "model": "", "needs_key": False},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-flash-latest", "needs_key": True},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini", "needs_key": True},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-20b", "needs_key": True},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-oss-20b:free", "needs_key": True},
    "custom": {"base_url": "", "model": "", "needs_key": False},
}


RETRY_STATUS = (429, 500, 502, 503, 504)
MAX_RETRIES = 3
MAX_WAIT_S = 45
_used = []              # (ms, tokens) dos pedidos dos últimos 60 s, para respeitar a cota por minuto
WAIT_SCALE = 1.0        # os testes diminuem isto para não esperar de verdade


class LLMError(Exception):
    pass


def _is_lan(url):
    h = url.split("://", 1)[-1].split("/", 1)[0].split(":")[0]
    return h in ("localhost", "127.0.0.1") or h.startswith(("192.168.", "10.", "172.")) or h.endswith(".local")


def explain_connect(base, err):
    msg = str(err)
    if "could not connect" in msg and _is_lan(base):
        msg += (". If the model runs on your computer: the address must be the computer's IP on this Wi-Fi (not localhost), and Ollama must "
                "listen on the network (OLLAMA_HOST=0.0.0.0, then restart Ollama).")
    return msg


def retry_wait(headers, text, attempt):
    """Quanto esperar antes de repetir: o Retry-After do provedor, ou o "try again in 7.2s" da mensagem (Groq), ou 4 s * tentativa."""
    wait = None
    ra = (headers or {}).get("retry-after")
    if ra:
        try:
            wait = float(ra)
        except ValueError:
            pass
    if wait is None:
        i = text.find("try again in ")
        if i >= 0:
            rest = text[i + 13:i + 40]
            total, num = 0.0, ""
            for ch in rest:
                if ch.isdigit() or ch == ".":
                    num += ch
                elif ch == "m" and num:
                    total += float(num) * 60
                    num = ""
                elif ch == "s" and num:
                    total += float(num)
                    num = ""
                    break
                else:
                    break
            if total:
                wait = total
    if wait is None:
        wait = 4 * attempt
    return int(min(MAX_WAIT_S, max(2, wait + 1)))


def is_daily_limit(text):
    """A cota do DIA (TPD/RPD) acabou: repetir não adianta e o ritmo por minuto não tem nada a ver com isso."""
    t = text.lower()
    return "per day" in t or "(tpd)" in t or "(rpd)" in t or "requests per day" in t


def learn_limit(text):
    """A Groq diz no 429: 'tokens per minute (TPM): Limit 8000, Used 7000, Requested 2000'. Devolve o limite por minuto, ou 0."""
    if is_daily_limit(text) or ("per minute" not in text.lower() and "(tpm)" not in text.lower()):
        return 0
    i = text.find("Limit ")
    if i < 0:
        return 0
    num = ""
    for ch in text[i + 6:i + 16]:
        if ch.isdigit():
            num += ch
        else:
            break
    return int(num) if num else 0


def _pace_wait(limit, need):
    """Segundos para esperar antes de enviar, para não passar da cota por minuto (soma dos últimos 60 s + este pedido)."""
    from . import compat
    now = compat.ticks_ms()
    while _used and compat.ticks_diff(now, _used[0][0]) > 60000:
        _used.pop(0)
    total = sum(t for _, t in _used)
    if not limit or total + need <= limit:
        return 0
    acc, i = total, 0
    while acc + need > limit and i < len(_used):
        acc -= _used[i][1]
        i += 1
    if i == 0:
        return 0
    return min(30, max(1, (60000 - compat.ticks_diff(now, _used[i - 1][0])) // 1000 + 1))


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
        if m["role"] == "user" and out and out[-1]["role"] == "user":
            out[-1]["content"] = str(out[-1]["content"]) + "\n" + str(m.get("content") or "")
            continue
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
    try:
        return await _chat(cfg, base, body)
    except http_client.HTTPError as e:
        raise LLMError(explain_connect(base, e))


async def _chat(cfg, base, body):
    payload = json.dumps(body, separators=(",", ":"))  # compacto: menos bytes e menos tokens contados por alguns provedores
    attempt = 0
    from . import compat, config, events
    import asyncio
    need = len(payload) // 3 + min(body["max_tokens"], 350)   # prompt + uma resposta típica (a resposta real quase nunca chega ao teto)
    wait = _pace_wait(cfg.get("llm_tpm", 0), need)
    if wait:
        events.emit("log", text="model busy: waiting %d s to stay under the provider's token limit" % wait)
        await asyncio.sleep(wait * WAIT_SCALE)
    while True:
        status, rh, data = await http_client.request("POST", base + "/chat/completions", _headers(cfg), payload,
                                                     cfg.get("llm_timeout_s", 120))
        full = data.decode("utf-8", "replace") if data else ""
        text = full[:600]
        # tool_use_failed / "Parsing failed": o modelo (gpt-oss na Groq, por exemplo) montou a chamada de ferramenta torta; costuma acertar na
        # segunda. O código do erro vem DEPOIS da geração que falhou (longa), por isso confere o corpo inteiro e não só o começo.
        bad_call = status == 400 and ("tool_use_failed" in full or "Parsing failed" in full or "could not be parsed" in full
                                      or "Failed to call a function" in full)
        daily = status == 429 and is_daily_limit(full)
        retryable = (status in RETRY_STATUS or bad_call) and not daily
        if status == 200 or not retryable or attempt >= MAX_RETRIES:
            break
        attempt += 1
        if status == 429 and not daily:
            lim = learn_limit(text)
            if lim and not cfg.get("llm_tpm"):  # aprende o limite por minuto e passa a respeitá-lo antes de enviar (salvo na configuração)
                cfg = config.save({"llm_tpm": int(lim * 0.85)})
                events.emit("log", text="provider limit learned: %d tokens per minute" % lim)
            elif cfg.get("llm_tpm", 0) > 2500:  # estourou mesmo se segurando: o limite real é menor que o aprendido, baixa 10 %
                cfg = config.save({"llm_tpm": int(cfg["llm_tpm"] * 0.9)})
                events.emit("log", text="still over the limit: now keeping to %d tokens per minute" % cfg["llm_tpm"])
        wait_s = retry_wait(rh, text, attempt)
        events.emit("log", text="model busy (HTTP %d), trying again in %d s (%d/%d)" % (status, wait_s, attempt, MAX_RETRIES))
        await asyncio.sleep(wait_s * WAIT_SCALE)
    if status != 200:
        if status == 429 and daily:
            i = full.find("try again in ")
            when = full[i + 13:i + 30].split(" ")[0].strip(".,") if i >= 0 else ""
            if when and when[-1].isdigit():
                when += "s"
            raise LLMError("The DAILY token quota of this model is used up. It resets by itself" + (" (try again in %s)" % when if when else "") +
                           ", or pick another model or provider in Settings (each model has its own quota). " + full[:160])
        if status == 429:
            raise LLMError("The provider's rate limit was hit (HTTP 429). Free plans limit tokens per minute: wait a minute and send again, "
                           "or pick another model or provider in Settings. " + text[:200])
        raise LLMError("HTTP %d: %s" % (status, text[:400]))
    try:
        resp = json.loads(data)
        msg = resp["choices"][0]["message"]
    except (ValueError, KeyError, IndexError):
        raise LLMError("unexpected reply: " + data[:300].decode("utf-8", "replace"))
    try:
        _used.append((compat.ticks_ms(), int(resp["usage"]["total_tokens"])))
    except (KeyError, TypeError, ValueError):
        _used.append((compat.ticks_ms(), need))
    msg["role"] = "assistant"
    return msg


async def list_models(cfg):
    base = cfg["llm_base_url"].rstrip("/")
    if not base:
        raise LLMError("no address yet: fill in the Address field first")
    try:
        status, _, data = await http_client.request("GET", base + "/models", _headers(cfg), None, 20)
    except http_client.HTTPError as e:
        raise LLMError(explain_connect(base, e))
    if status != 200:
        raise LLMError("HTTP %d: %s" % (status, data[:200].decode("utf-8", "replace") if data else ""))
    items = json.loads(data).get("data", [])
    ids = [str(m.get("id", "")) for m in items]
    return sorted([i[7:] if i.startswith("models/") else i for i in ids if i])
