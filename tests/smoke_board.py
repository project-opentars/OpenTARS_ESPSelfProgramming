# Teste de fumaça NA PLACA (MicroPython): mpremote connect /dev/ttyACM0 run tests/smoke_board.py
# Roda programas em threads, uma ferramenta, desenha na OLED (se houver) e acende o LED.
import sys
sys.path.append("/lib")
sys.path.append("/skills")
import asyncio
from core import programs, tools

falhas = [0]


def conferir(nome, ok, det=""):
    print(("ok   " if ok else "FALHA"), nome, "" if ok else str(det)[:300])
    if not ok:
        falhas[0] += 1


async def main():
    p = programs.start(name="laco", code="n=0\nwhile True:\n    n+=1\n    delay(20)\n")
    await asyncio.sleep(0.5)
    res = programs.stop("laco")
    conferir("programa em thread para com delay()", res["stopped"] == ["laco"], res)
    p = programs.start(code="print(1/0)")
    await programs.await_done(p, 3000)
    conferir("erro traz o traceback", p.status == "error" and "ZeroDivisionError" in p.error, p.error)

    r = await tools.call("run_code", {"code": "import tars, gfx\nd = tars.oled()\nprint('oled', d is not None)\n"
                                      "if d:\n    g = gfx.Gfx(d)\n    a = 0\n    for _ in range(40):\n"
                                      "        d.fill(0); g.wire(gfx.CUBE, a*0.7, a, a*0.4); d.text('openTARS SP', 20, 0); d.show(); a += 0.1; delay(10)\n"
                                      "tars.led(0, 30, 0); delay(400); tars.led(0, 0, 0)\nprint('fim')", "timeout_s": 20})
    conferir("tars + gfx na OLED real (cubo) e LED", "fim" in r, r)
    print("   ", r.split("\n")[1] if "\n" in r else r)

    print("\n%d falha(s)" % falhas[0])


asyncio.run(main())
