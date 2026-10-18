# Wi-Fi e ESP-NOW. As placas se anunciam a cada 10 s (broadcast), trocam textos e mandam código para outra placa rodar.
# Quadro ESP-NOW: b"OT" + tipo (1 byte) + id (2) + índice (1) + total (1) + até 240 bytes de dados.
import asyncio
import json
import os
from . import compat, config, events

T_HELLO, T_TEXT, T_RUN, T_RESULT = 1, 2, 3, 4
CHUNK = 240
BCAST = b"\xff" * 6
AP_IP = "192.168.71.1"   # longe do 192.168.4.x, que é a faixa de muitos roteadores (e do AP padrão do ESP32)

_st = {"mode": "offline", "ip": "", "ssid": "", "channel": None, "name": "", "mac": "", "rssi": None}
_wlan = None
_esp = None
_peers = {}        # mac(bytes) -> {"name", "mac", "rssi", "seen", "ip"}
_parts = {}        # (mac, tipo, id) -> {"total": n, "chunks": {i: bytes}, "t": ms}
_waiting = {}      # id -> {"done": bool, "text": str}
_inboxes = []
_send_lock = None
ESPNOW_FACTORY = None   # os testes trocam por um ESP-NOW de mentira


def mac_str(mac):
    return ":".join("%02x" % b for b in mac)


def _parse_mac(s):
    try:
        b = bytes(int(x, 16) for x in s.split(":"))
        return b if len(b) == 6 else None
    except ValueError:
        return None


def name():
    return _st["name"]


def status():
    return dict(_st)


def peers_info():
    now = compat.ticks_ms()
    out = []
    for p in _peers.values():
        age = compat.ticks_diff(now, p["seen"]) // 1000
        out.append({"name": p["name"], "mac": p["mac"], "rssi": p.get("rssi"), "ip": p.get("ip", ""), "seen_s_ago": age,
                    "online": age < 35})
    return sorted(out, key=lambda x: x["name"])


# ---------------- Wi-Fi ----------------
async def start_wifi():
    global _wlan
    cfg = config.get()
    try:
        import network
    except ImportError:  # CPython (testes): finge uma rede local
        _st.update({"mode": "sim", "ip": "127.0.0.1", "name": cfg.get("name") or "opentars-sim", "mac": "00:00:00:00:00:00"})
        return
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    mac = sta.config("mac")
    _st["mac"] = mac_str(mac)
    _st["name"] = cfg.get("name") or "opentars-%02x%02x" % (mac[4], mac[5])
    try:
        network.hostname(_st["name"])  # vira <nome>.local na rede (mDNS)
    except Exception:
        pass
    _wlan = sta
    if cfg.get("wifi_ssid"):
        events.emit("log", text="connecting to Wi-Fi " + cfg["wifi_ssid"])
        sta.connect(cfg["wifi_ssid"], cfg.get("wifi_password", ""))
        for _ in range(40):
            if sta.isconnected():
                break
            await asyncio.sleep(0.5)
    if sta.isconnected():
        try:
            sta.config(pm=sta.PM_NONE)  # sem economia de energia: o ESP-NOW precisa ouvir o tempo todo
        except Exception:
            pass
        _st.update({"mode": "sta", "ip": sta.ifconfig()[0], "ssid": cfg["wifi_ssid"], "channel": sta.config("channel")})
        try:
            _st["rssi"] = sta.status("rssi")
        except Exception:
            pass
        return
    # sem Wi-Fi: rede própria, aberta, para configurar pelo celular (e o ESP-NOW segue no canal escolhido)
    if cfg.get("wifi_ssid"):
        sta.disconnect()
    ch = int(cfg.get("espnow_channel") or 1)
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    try:
        ap.config(essid=_st["name"], authmode=0, channel=ch)
    except Exception:
        ap.config(essid=_st["name"], channel=ch)
    try:
        ap.ifconfig((AP_IP, "255.255.255.0", AP_IP, AP_IP))
    except Exception:
        pass
    _st.update({"mode": "ap", "ip": ap.ifconfig()[0], "ssid": _st["name"], "channel": ch})


def scan_wifi():
    if not _wlan:
        return []
    seen = {}
    for r in _wlan.scan():
        ssid = r[0].decode("utf-8", "replace")
        if ssid and (ssid not in seen or r[3] > seen[ssid]["rssi"]):
            seen[ssid] = {"ssid": ssid, "rssi": r[3], "channel": r[2], "open": r[4] == 0}
    return sorted(seen.values(), key=lambda x: -x["rssi"])


# ---------------- ESP-NOW ----------------
def start_espnow():
    global _esp, _send_lock
    import _thread
    _send_lock = _thread.allocate_lock()
    try:
        if ESPNOW_FACTORY:
            _esp = ESPNOW_FACTORY()
        else:
            import espnow
            _esp = espnow.ESPNow()
        _esp.active(True)
        _add_peer(BCAST)
        events.emit("log", text="ESP-NOW on, channel %s" % _st.get("channel"))
    except Exception as e:
        _esp = None
        events.emit("log", text="ESP-NOW not available: %s" % e)


def _add_peer(mac):
    try:
        _esp.add_peer(mac)
    except OSError:
        pass  # já estava na lista


def _frame(kind, mid, idx, total, data):
    return b"OT" + bytes([kind, (mid >> 8) & 255, mid & 255, idx, total]) + data


def _send_raw(mac, data):
    """Envia um quadro; em unicast confere a confirmação e tenta até 3 vezes."""
    if not _esp:
        return False
    with _send_lock:
        if mac != BCAST:
            _add_peer(mac)
        for _ in range(3):
            try:
                ok = _esp.send(mac, data, mac != BCAST)
            except OSError:
                ok = False
            if ok or mac == BCAST:
                return True
            compat.sleep_ms(15)
    return False


def _send_message(mac, kind, mid, payload):
    if isinstance(payload, str):
        payload = payload.encode()
    total = max(1, (len(payload) + CHUNK - 1) // CHUNK)
    if total > 255:
        raise ValueError("message too long for ESP-NOW (max %d bytes)" % (255 * CHUNK))
    for i in range(total):
        if not _send_raw(mac, _frame(kind, mid, i, total, payload[i * CHUNK:(i + 1) * CHUNK])):
            return False
    return True


def _resolve(to):
    to = (to or "").strip()
    if to.lower() in ("all", "*", "broadcast"):
        return BCAST
    m = _parse_mac(to) if ":" in to else None
    if m:
        return m
    for mac, p in _peers.items():
        if p["name"].lower() == to.lower():
            return mac
    return None


def _new_id():
    return int.from_bytes(os.urandom(2), "big")


def send_hello(mac=BCAST):
    info = {"n": _st["name"], "ip": _st["ip"], "ch": _st["channel"], "v": 1}
    _send_message(mac, T_HELLO, _new_id(), json.dumps(info))


def send_text_sync(to, text):
    mac = _resolve(to)
    if mac is None:
        return "error: no board called '%s' (known: %s)" % (to, ", ".join(p["name"] for p in _peers.values()) or "none")
    ok = _send_message(mac, T_TEXT, _new_id(), text)
    return "sent" if ok else "error: the other board did not confirm (off, out of range or on another Wi-Fi channel)"


async def send_text(to, text):
    return send_text_sync(to, text)


async def remote_run(to, code, timeout_s):
    mac = _resolve(to)
    if mac is None or mac == BCAST:
        return "error: name one board (known: %s)" % (", ".join(p["name"] for p in _peers.values()) or "none")
    mid = _new_id()
    _waiting[mid] = {"done": False, "text": ""}
    payload = ("%d\n" % timeout_s) + code
    if not _send_message(mac, T_RUN, mid, payload):
        del _waiting[mid]
        return "error: the other board did not confirm"
    end = compat.ticks_ms() + (timeout_s + 5) * 1000
    while not _waiting[mid]["done"] and compat.ticks_diff(end, compat.ticks_ms()) > 0:
        await asyncio.sleep(0.05)
    res = _waiting.pop(mid)
    return res["text"] if res["done"] else "error: no answer from %s within %d s" % (_peers.get(mac, {}).get("name", to), timeout_s + 5)


class Inbox:
    """Fila de mensagens para um programa: inbox = tars.inbox(); inbox.get(timeout_ms) -> (remetente, texto) ou None."""
    def __init__(self):
        self.items = []
        self.polled = compat.ticks_ms()
        _inboxes.append(self)

    def get(self, timeout_ms=0):
        end = compat.ticks_ms() + timeout_ms
        while True:
            self.polled = compat.ticks_ms()
            if self.items:
                return self.items.pop(0)
            if compat.ticks_diff(end, compat.ticks_ms()) <= 0:
                return None
            compat.sleep_ms(20)


def _deliver_text(sender, text):
    events.emit("espnow_msg", sender=sender, text=text[:500])
    now = compat.ticks_ms()
    for q in list(_inboxes):
        if compat.ticks_diff(now, q.polled) > 120000:  # programa que parou de ler há 2 min: solta a fila
            _inboxes.remove(q)
            continue
        q.items.append((sender, text))
        if len(q.items) > 30:
            q.items.pop(0)


async def _handle_run(mac, mid, payload):
    from . import programs
    text = payload.decode("utf-8", "replace")
    first, _, code = text.partition("\n")
    try:
        timeout = int(first)
    except ValueError:
        timeout, code = 15, text
    sender = _peers.get(mac, {}).get("name", mac_str(mac))
    events.emit("log", text="running code sent by " + sender)
    try:
        p = programs.start(code=code, name="from-%s-%d" % (sender, mid))
        done = await programs.await_done(p, timeout * 1000)
        out = "\n".join(p.log[-60:]) or "(printed nothing)"
        result = "%s: status=%s\n%s%s" % (_st["name"], p.status, out, "" if done else "\n(still running there as " + p.name + ")")
    except Exception as e:
        result = "%s: error: %s" % (_st["name"], e)
    _send_message(mac, T_RESULT, mid, result[:4000])


def _on_frame(mac, data):
    if len(data) < 7 or data[:2] != b"OT":
        return None
    kind, mid, idx, total = data[2], (data[3] << 8) | data[4], data[5], data[6]
    key = (mac, kind, mid)
    if total <= 1:
        payload = bytes(data[7:])
    else:
        entry = _parts.setdefault(key, {"total": total, "chunks": {}, "t": compat.ticks_ms()})
        entry["chunks"][idx] = bytes(data[7:])
        if len(entry["chunks"]) < total:
            return None
        payload = b"".join(entry["chunks"][i] for i in range(total))
        del _parts[key]
    return kind, mid, payload


async def _dispatch(mac, kind, mid, payload):
    if kind == T_HELLO:
        try:
            info = json.loads(payload)
        except ValueError:
            return
        new = mac not in _peers
        rssi = None
        try:
            rssi = _esp.peers_table[mac][0]
        except Exception:
            pass
        _peers[mac] = {"name": info.get("n", mac_str(mac)), "mac": mac_str(mac), "ip": info.get("ip", ""), "rssi": rssi,
                       "seen": compat.ticks_ms()}
        if new:
            events.emit("peer", name=_peers[mac]["name"], mac=mac_str(mac))
            send_hello(mac)  # responde direto: a outra placa me descobre na hora
    elif kind == T_TEXT:
        sender = _peers.get(mac, {}).get("name", mac_str(mac))
        _deliver_text(sender, payload.decode("utf-8", "replace"))
    elif kind == T_RUN:
        asyncio.create_task(_handle_run(mac, mid, payload))
    elif kind == T_RESULT:
        if mid in _waiting:
            _waiting[mid].update({"done": True, "text": payload.decode("utf-8", "replace")})


async def rx_loop():
    while True:
        if _esp is None:
            await asyncio.sleep(1)
            continue
        try:
            while _esp.any():
                mac, data = _esp.irecv(0)
                if mac is None:
                    break
                got = _on_frame(bytes(mac), data)
                if got:
                    await _dispatch(bytes(mac), *got)
        except Exception as e:
            events.emit("log", text="ESP-NOW receive error: %s" % e)
        now = compat.ticks_ms()
        for k in [k for k, v in _parts.items() if compat.ticks_diff(now, v["t"]) > 10000]:
            del _parts[k]  # pedaços que nunca completaram
        await asyncio.sleep(0.03)


async def hello_loop():
    while True:
        if _esp is not None:
            try:
                send_hello()
            except Exception:
                pass
        await asyncio.sleep(10)


async def start():
    await start_wifi()
    start_espnow()
    asyncio.create_task(rx_loop())
    asyncio.create_task(hello_loop())
