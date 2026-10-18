# Configuração guardada em /data/config.json. Campos que faltam usam DEFAULTS.
# Todo valor que entra (pela página, pelo agente ou de um arquivo antigo) passa por _coerce: tipo errado ou fora da faixa é recusado
# e fica o valor anterior. Um valor ruim aqui não pode impedir a placa de ligar.
import json
from . import compat

PATH = "/data/config.json"

DEFAULTS = {
    "name": "",                 # nome da placa na rede (vazio = opentars-xxxx)
    "lang": "en",               # en ou pt (a página também guarda a escolha do navegador)
    "wifi_ssid": "",
    "wifi_password": "",
    "espnow_channel": 1,        # canal do ESP-NOW quando a placa NÃO está no Wi-Fi (no Wi-Fi vale o canal do roteador)
    "harness": "",              # programa de IA do computador que faz o trabalho (claude, codex...); vazio = o primeiro que a ponte achar
    "harness_model": "",        # modelo pedido ao programa; vazio = o padrão dele
    "autostart": [],            # programas que rodam ao ligar: [{"name": ..., "path": ...}]
    "oled": {"sda": 9, "scl": 8, "addr": 60, "width": 128, "height": 64},
    "rgb_led_pin": 48,
    "tz_offset_min": 0,         # fuso horário em minutos em relação ao UTC (São Paulo = -180)
}

RANGES = {
    "espnow_channel": (1, 13), "rgb_led_pin": (0, 48), "tz_offset_min": (-720, 840),
}
OLED_RANGES = {"sda": (0, 48), "scl": (0, 48), "addr": (8, 119), "width": (64, 128), "height": (32, 64)}
TEXT_MAX = 400

_cfg = None


def _int_in(v, lo, hi):
    if isinstance(v, bool):
        raise ValueError("not a number")
    n = int(float(v))
    if not lo <= n <= hi:
        raise ValueError("out of range")
    return n


def _coerce(key, value, current):
    """Valor validado para a chave, ou ValueError. current é o valor atual (para mesclar o dicionário da OLED)."""
    d = DEFAULTS[key]
    if key in RANGES:
        return _int_in(value, *RANGES[key])
    if isinstance(d, str):
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise ValueError("not text")
        s = str(value).strip()
        if len(s) > TEXT_MAX:
            raise ValueError("too long")
        if key == "lang" and s not in ("en", "pt"):
            raise ValueError("lang must be en or pt")
        return s
    if key == "oled":
        if not isinstance(value, dict):
            raise ValueError("not an object")
        out = dict(current if isinstance(current, dict) else d)
        for k, v in value.items():
            if k in OLED_RANGES:
                out[k] = _int_in(v, *OLED_RANGES[k])
        return out
    if key == "autostart":
        if not isinstance(value, list):
            raise ValueError("not a list")
        return [{"name": str(a.get("name", ""))[:60], "path": str(a["path"])[:TEXT_MAX]}
                for a in value if isinstance(a, dict) and isinstance(a.get("path"), str) and a["path"].startswith("/")][:8]
    raise ValueError("unknown key")


def load():
    global _cfg
    data = {}
    txt = compat.read_text(PATH)
    if txt:
        try:
            data = json.loads(txt)
        except ValueError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    cfg = dict(DEFAULTS)
    changed = False
    for k, v in data.items():
        if k not in DEFAULTS:
            continue
        try:
            cfg[k] = _coerce(k, v, cfg[k])
        except (ValueError, TypeError, KeyError):
            changed = True  # valor estragado no arquivo: fica o padrão
    _cfg = cfg
    if changed:
        try:
            compat.write_text(PATH, json.dumps(cfg))
        except OSError:
            pass
    return cfg


def get():
    return _cfg if _cfg is not None else load()


def save(updates):
    """Grava só o que passa na validação. Devolve a config; as chaves recusadas ficam em last_rejected."""
    cfg = get()
    rejected = []
    for k, v in updates.items():
        if k not in DEFAULTS:
            rejected.append(k)
            continue
        try:
            cfg[k] = _coerce(k, v, cfg.get(k))
        except (ValueError, TypeError, KeyError):
            rejected.append(k)
    compat.write_text(PATH, json.dumps(cfg))
    global last_rejected
    last_rejected = rejected
    return cfg


last_rejected = []   # chaves da última gravação que a validação recusou (MicroPython não deixa pôr atributo em função)


def public():
    """Config para a página: a senha do Wi-Fi vai mascarada."""
    cfg = dict(get())
    cfg["wifi_password"] = "*" * 8 if cfg.get("wifi_password") else ""
    return cfg
