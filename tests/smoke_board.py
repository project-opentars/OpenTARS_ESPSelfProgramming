# Teste de fumaça NA PLACA (MicroPython): mpremote connect /dev/ttyACM0 run tests/smoke_board.py
# Sobe um "modelo" de mentira na própria placa, conversa com o agente pela API HTTP, roda programas em threads,
# desenha na OLED (se houver) e acende o LED. No fim apaga a configuração e a conversa de teste.
import sys
sys.path.append("/lib")
sys.path.append("/skills")
import asyncio
import json
import os
from core import compat, config, http_client, programs, tools, hw
from core.api import make_server

falhas = [0]


def conferir(nome, ok, det=""):
    print(("ok   " if ok else "FALHA"), nome, "" if ok else str(det)[:300])
    if not ok:
        falhas[0] += 1


async def modelo(reader, writer):
    line = await reader.readline()
    n = 0
    while True:
        h = await reader.readline()
        if h in (b"\r\n", b""):
            break
        if h.lower().startswith(b"content-length:"):
            n = int(h.split(b":")[1])
    body = json.loads(await reader.readexactly(n))
    tool_msgs = [m for m in body["messages"] if m["role"] == "tool"]
    if not tool_msgs:
        msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function",
               "function": {"name": "run_code", "arguments": json.dumps({"code": "print('answer', 6 * 7)"})}}]}
    else:
        msg = {"role": "assistant", "content": "board said " + tool_msgs[-1]["content"].split("\n")[1]}
    payload = json.dumps({"choices": [{"message": msg}]}).encode()
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(payload) + payload)
    await writer.drain()
    writer.close()


async def get(path):
    st, _, data = await http_client.request("GET", "http://127.0.0.1:8080" + path, None, None, 15)
    return st, data


async def post(path, obj):
    st, _, data = await http_client.request("POST", "http://127.0.0.1:8080" + path, {"Content-Type": "application/json"},
                                            json.dumps(obj), 15)
    return st, json.loads(data)


async def main():
    config.load()
    old_cfg = compat.read_text(config.PATH)
    await asyncio.start_server(modelo, "127.0.0.1", 8081)
    await make_server().start("0.0.0.0", 8080)
    st, data = await get("/")
    conferir("página servida com gzip", st == 200 and data[:2] == b"\x1f\x8b", (st, data[:10]))
    st, r = await post("/api/config", {"llm_base_url": "http://127.0.0.1:8081/v1", "llm_model": "fake", "llm_api_key": "k1234567"})
    conferir("config salva e mascarada", r["config"]["llm_api_key"] == "********4567", r)
    st, r = await post("/api/chat", {"text": "6 x 7?"})
    conferir("pedido aceito", st == 200, r)
    last, kinds, final = 0, [], ""
    for _ in range(200):
        st, data = await get("/api/events?since=%d" % last)
        for e in json.loads(data)["events"]:
            last = e["id"]
            kinds.append(e["kind"])
            if e["kind"] in ("assistant", "error"):
                final = e["text"]
        if "state" in kinds and final:
            break
        await asyncio.sleep(0.1)
    conferir("agente chamou run_code, rodou numa thread e respondeu", "tool_call" in kinds and "answer 42" in final, (kinds, final))

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

    # limpa o que o teste deixou
    for f in ("/data/chat.json",):
        try:
            os.remove(f)
        except OSError:
            pass
    if old_cfg is None:
        try:
            os.remove(config.PATH)
        except OSError:
            pass
    else:
        compat.write_text(config.PATH, old_cfg)
    print("\n%d falha(s)" % falhas[0])


asyncio.run(main())
