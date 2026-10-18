# openTARS Self-Programming: inicia a rede, a página, o ESP-NOW e os programas automáticos.
# Segurar o botão BOOT ao ligar = modo seguro (não roda os programas automáticos, para escapar de um programa que trava).
import asyncio
import gc
import sys

sys.path.append("/lib")
sys.path.append("/skills")

from core import api, config, events, hw, net, programs


def _safe_mode():
    try:
        from machine import Pin
        return Pin(0, Pin.IN, Pin.PULL_UP).value() == 0
    except Exception:
        return False


async def main():
    cfg = config.load()
    safe = _safe_mode()
    hw.led(0, 0, 40)
    await net.start()
    st = net.status()
    hw.led(0, 40, 0) if st["mode"] == "sta" else hw.led(40, 25, 0)
    hw.show_boot_info(st)
    await api.make_server().start(port=80)
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
