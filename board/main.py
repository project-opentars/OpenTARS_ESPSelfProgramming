# openTARS Self-Programming: inicia a rede, a página, o ESP-NOW e os programas automáticos.
# Segurar o botão BOOT ao ligar = modo seguro (não roda os programas automáticos, para escapar de um programa que trava).
import asyncio
import gc
import sys

sys.path.append("/lib")
sys.path.append("/skills")

from core import api, compat, config, events, hw, net, programs

CAUSES = {1: "power-on", 2: "hard reset or crash", 3: "watchdog", 4: "deep sleep", 5: "soft reset"}


STATE = "/data/state.json"


def _log_boot():
    """Guarda o motivo de cada reinício em /data/boot.log (últimas 30 linhas). Junto vai o diário da vida anterior: se ela não acabou
    com um reinício limpo (botão da página), a linha diz quanto tempo durou e quais programas rodavam: ajuda a achar travamentos."""
    import json
    try:
        import machine
        cause = CAUSES.get(machine.reset_cause(), str(machine.reset_cause()))
    except Exception:
        cause = "unknown"
    extra = ""
    try:
        prev = json.loads(compat.read_text(STATE, "") or "{}")
        if prev and not prev.get("clean"):
            extra = " | previous run ended unexpectedly after %ss, free %s KB, programs: %s" % (
                prev.get("up"), (prev.get("free") or 0) // 1024, ",".join(prev.get("progs") or []) or "none")
    except Exception:
        pass
    old = (compat.read_text("/data/boot.log", "") or "").splitlines()[-29:]
    compat.write_text("/data/boot.log", "\n".join(old + ["boot #%d: %s%s" % (len(old) + 1, cause, extra)]) + "\n")
    api.BOOT_CAUSE = cause + extra
    events.emit("log", text="boot: " + cause + extra)


async def journal_loop():
    """Escreve o estado em /data/state.json quando a lista de programas muda e a cada 2 min (pouco desgaste da flash)."""
    import json
    last_progs, last_write = None, -999999
    while True:
        names = sorted(p.name for p in programs._programs.values() if p.status in ("starting", "running"))
        now = compat.ticks_ms()
        if names != last_progs or compat.ticks_diff(now, last_write) > 120000:
            try:
                compat.write_text(STATE, json.dumps({"clean": False, "up": now // 1000, "progs": names, "free": compat.mem_info()["free"]}))
            except Exception:
                pass
            last_progs, last_write = names, now
        await asyncio.sleep(5)


def _safe_mode():
    try:
        from machine import Pin
        return Pin(0, Pin.IN, Pin.PULL_UP).value() == 0
    except Exception:
        return False


async def ntp_loop():
    """Sincroniza o relógio ao ligar e a cada 3 horas, numa thread (o ntptime bloqueia até 3 s)."""
    import _thread
    import tars
    while True:
        if net.status()["mode"] == "sta":
            try:
                _thread.start_new_thread(tars.sync_time, ())
            except Exception:
                pass
        await asyncio.sleep(3 * 3600)


async def main():
    cfg = config.load()
    _log_boot()
    safe = _safe_mode()
    hw.led(0, 0, 40)
    await net.start()
    st = net.status()
    hw.led(0, 40, 0) if st["mode"] == "sta" else hw.led(40, 25, 0)
    hw.show_boot_info(st)
    await api.make_server().start(port=80)
    asyncio.create_task(ntp_loop())
    asyncio.create_task(journal_loop())
    events.emit("log", text="ready at http://%s (%s)" % (st["ip"], st["mode"]))
    print("openTARS Self-Programming ready: http://%s  mode=%s  name=%s" % (st["ip"], st["mode"], st["name"]))
    if safe:
        events.emit("log", text="safe mode: autostart programs skipped (BOOT held at power-on)")
    else:
        for a in cfg.get("autostart", []):
            try:
                programs.start(name=a.get("name"), path=a.get("path"))
            except Exception as e:
                events.emit("log", text="autostart %s failed: %s" % (a.get("path"), e))
    await asyncio.sleep(3)
    hw.led(0, 0, 0)
    while True:
        await asyncio.sleep(10)
        gc.collect()


asyncio.run(main())
