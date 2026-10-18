# Configuração guardada em /data/config.json. Campos que faltam usam DEFAULTS.
import json
from . import compat

PATH = "/data/config.json"

DEFAULTS = {
    "name": "",                 # nome da placa na rede (vazio = opentars-xxxx)
    "lang": "en",               # en ou pt (a página também guarda a escolha do navegador)
    "wifi_ssid": "",
    "wifi_password": "",
    "espnow_channel": 1,        # canal do ESP-NOW quando a placa NÃO está no Wi-Fi (no Wi-Fi vale o canal do roteador)
    "llm_preset": "gemini",
    "llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "llm_api_key": "",
    "llm_model": "gemini-flash-latest",
    "llm_max_tokens": 4096,
    "llm_timeout_s": 120,
    "agent_max_rounds": 12,
    "autostart": [],            # programas que rodam ao ligar: [{"name": ..., "path": ...}]
    "oled": {"sda": 9, "scl": 8, "addr": 60, "width": 128, "height": 64},
    "rgb_led_pin": 48,
}

_cfg = None


def load():
    global _cfg
    data = {}
    txt = compat.read_text(PATH)
    if txt:
        try:
            data = json.loads(txt)
        except ValueError:
            data = {}
    cfg = dict(DEFAULTS)
    cfg.update(data)
    _cfg = cfg
    return cfg


def get():
    return _cfg if _cfg is not None else load()


def save(updates):
    cfg = get()
    for k, v in updates.items():
        if k in DEFAULTS:
            cfg[k] = v
    compat.write_text(PATH, json.dumps(cfg))
    return cfg


def public():
    """Config para a página: a chave da API vai mascarada."""
    cfg = dict(get())
    key = cfg.get("llm_api_key") or ""
    cfg["llm_api_key"] = ("*" * 8 + key[-4:]) if len(key) > 4 else ("*" * len(key))
    cfg["wifi_password"] = "*" * 8 if cfg.get("wifi_password") else ""
    return cfg
