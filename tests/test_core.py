#!/usr/bin/env python3
"""Testes do núcleo no Python do PC (sem a placa): servidor web, ponte de ponta a ponta com um "claude" de mentira,
programas em threads, ferramentas e duas "placas" ESP-NOW simuladas. Uso: python3 tests/test_core.py"""
import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "board"))
sys.path.insert(0, os.path.join(RAIZ, "board", "lib"))

from core import compat  # noqa: E402

TMP = tempfile.mkdtemp(prefix="otsp-")
compat.ROOT = TMP
os.system(sys.executable + " " + os.path.join(RAIZ, "tools", "build_web.py") + " >/dev/null")
shutil.copytree(os.path.join(RAIZ, "board", "www"), os.path.join(TMP, "www"))

from core import agent, config, events, net, programs, tools, web  # noqa: E402
from core.api import make_server  # noqa: E402

falhas = 0


def conferir(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else "\n     " + str(detalhe)[:600])
    if not ok:
        falhas += 1


def _req(method, port, path, body):
    data = body if isinstance(body, (str, type(None))) else json.dumps(body)
    r = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data and data.encode(), method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as f:
            return f.status, f.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


async def http(port, method, path, body=None, raw=False):
    status, data = await asyncio.get_running_loop().run_in_executor(None, _req, method, port, path, body)
    return status, (data.decode() if raw else json.loads(data or b"{}"))


# "claude" de mentira: lê o pedido, chama a ferramenta pelo comando que a ponte ensinou e responde com o que a placa imprimiu.
FAKE_HARNESS = """#!/usr/bin/env python3
import re, subprocess, sys
prompt = sys.argv[sys.argv.index("-p") + 1]
me, board = re.search(r"python3 (\\S+) tool (\\S+) NAME", prompt).groups()
out = subprocess.run([sys.executable, me, "tool", board, "run_code", "timeout_s=5"], input="x = 6 * 7\\nprint('answer', x)\\n",
                     capture_output=True, text=True).stdout
print("The board printed: " + out.split("\\n")[1])
"""


# ---------------- ESP-NOW de mentira: um "ar" que liga duas placas ----------------
class Ar:
    def __init__(self):
        self.radios = {}


class FakeESPNow:
    def __init__(self, ar, mac):
        self.ar, self.mac, self.fila, self.peers_table = ar, mac, [], {}
        ar.radios[mac] = self

    def active(self, on):
        pass

    def add_peer(self, mac):
        pass

    def send(self, mac, data, sync=True):
        alvos = [r for m, r in self.ar.radios.items() if m != self.mac and (mac == net.BCAST or m == mac)]
        for r in alvos:
            r.fila.append((self.mac, bytes(data)))
            r.peers_table[self.mac] = [-40, 0]
        return bool(alvos)

    def any(self):
        return bool(self.fila)

    def irecv(self, timeout):
        return self.fila.pop(0) if self.fila else (None, None)


def segunda_placa():
    """Carrega uma segunda cópia do módulo net (outra placa, mesma "física")."""
    spec = importlib.util.spec_from_file_location("core.net_b", os.path.join(RAIZ, "board", "core", "net.py"))
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "core"
    spec.loader.exec_module(mod)
    return mod


async def principal():
    config.load()
    srv = await make_server().start("127.0.0.1", 0)
    porta = srv.sockets[0].getsockname()[1]

    # --- web: estático com gzip, ponte servida pela placa e 404 ---
    st, data = await asyncio.get_running_loop().run_in_executor(None, _req, "GET", porta, "/", None)
    conferir("página inicial servida (gzip)", st == 200 and data[:2] == b"\x1f\x8b", (st, data[:20]))
    st, txt = await http(porta, "GET", "/bridge.py", raw=True)
    conferir("a placa entrega a ponte", st == 200 and "openTARS bridge" in txt, st)
    st, _ = await http(porta, "GET", "/api/nada")
    conferir("rota inexistente dá 404", st == 404)
    conferir("unquote com %, + e acento", web.unquote("a%20b+c%C3%A9") == "a b cé", web.unquote("a%20b+c%C3%A9"))

    # --- config: valores ruins são recusados ---
    st, r = await http(porta, "POST", "/api/config", {"harness": "codex", "espnow_channel": 99, "wifi_password": "********"})
    conferir("config valida faixa e guarda o programa de IA", r["rejected"] == ["espnow_channel"] and config.get()["harness"] == "codex", r)
    await http(porta, "POST", "/api/config", {"harness": ""})

    # --- sem ponte conectada: erro claro, pedido não fica no histórico ---
    st, r = await http(porta, "POST", "/api/chat", {"text": "oi"})
    await asyncio.sleep(0.3)
    evs = events.since(0)
    conferir("sem computador conectado dá erro no_bridge e não grava o pedido", any(e["kind"] == "error" and e["reason"] == "no_bridge" for e in evs) and not agent.agent.history, evs[-3:])
    st, r = await http(porta, "GET", "/api/status")
    conferir("status diz que a ponte não está conectada", r["bridge"]["connected"] is False, r["bridge"])

    # --- ponte de ponta a ponta: bridge.py de verdade + "claude" de mentira ---
    bindir = os.path.join(TMP, "bin")
    os.makedirs(bindir)
    with open(os.path.join(bindir, "claude"), "w") as f:
        f.write(FAKE_HARNESS)
    os.chmod(os.path.join(bindir, "claude"), 0o755)
    env = dict(os.environ, PATH=bindir + os.pathsep + "/usr/bin:/bin", HOME=TMP)
    ponte = await asyncio.create_subprocess_exec(sys.executable, os.path.join(RAIZ, "pc", "bridge.py"), "http://127.0.0.1:%d" % porta, env=env,
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    for _ in range(60):
        await asyncio.sleep(0.1)
        st, r = await http(porta, "GET", "/api/status")
        if r["bridge"]["connected"]:
            break
    conferir("a ponte conecta e lista o programa de IA que achou", r["bridge"]["connected"] and r["bridge"]["available"] == ["claude"], r["bridge"])
    last = events.last_id()
    st, r = await http(porta, "POST", "/api/chat", {"text": "quanto é 6 vezes 7? rode na placa"})
    conferir("pedido aceito", st == 200, r)
    st, r = await http(porta, "POST", "/api/chat", {"text": "outro"})
    conferir("segundo pedido enquanto ocupado dá 409", st == 409, (st, r))
    vistos = []
    for _ in range(200):
        st, r = await http(porta, "GET", "/api/events?since=%d" % last)
        for e in r["events"]:
            vistos.append(e)
            last = e["id"]
        if any(e["kind"] == "state" and e["state"] in ("done", "error") for e in vistos):
            break
        await asyncio.sleep(0.1)
    final = [e for e in vistos if e["kind"] == "assistant"]
    conferir("eventos: user, tool_call, tool_result, assistant", all(k in [e["kind"] for e in vistos] for k in ("user", "tool_call", "tool_result", "assistant")), vistos)
    conferir("o código rodou na placa e a resposta voltou pela ponte", final and "answer 42" in final[-1]["text"], [e for e in vistos if e["kind"] in ("tool_result", "assistant", "error")])
    st, r = await http(porta, "GET", "/api/chat/history")
    conferir("histórico reconstrói a conversa", [i["kind"] for i in r["items"]][:2] == ["user", "tool_call"], r)
    st, r = await http(porta, "POST", "/api/tool", {"name": "nao_existe", "args": {}})
    conferir("ferramenta inexistente dá 400 com a lista", st == 400 and "run_code" in r["error"], r)
    st, r = await http(porta, "POST", "/api/chat", {"text": "pare tudo"})
    await asyncio.sleep(0.3)
    conferir("'pare tudo' é tratado pela placa", any(e["kind"] == "assistant" and "program" in e["text"].lower() for e in events.since(last)), events.since(last)[-2:])
    ponte.kill()
    await ponte.wait()

    # --- programas: laço com delay para quando pedido; erro traz a linha ---
    p = programs.start(name="laco", code="n = 0\nwhile True:\n    n += 1\n    if n % 5 == 0: print('volta', n)\n    delay(10)\n")
    await asyncio.sleep(0.3)
    res = programs.stop("laco")
    conferir("programa com delay() para quando pedem", res["stopped"] == ["laco"] and p.status == "stopped" and any("volta" in x for x in p.log), (res, p.status, p.log[-3:]))
    p = programs.start(code="a = 1\nb = 0\nprint(a / b)\n")
    await programs.await_done(p, 3000)
    r = await tools.call("run_code", {"code": "import modulo_que_nao_existe"})
    conferir("run_code devolve o traceback do erro (não 'printed nothing')", "ImportError" in r or "ModuleNotFoundError" in r or "No module" in r, r)
    conferir("erro no programa guarda o traceback com a linha", p.status == "error" and "line 3" in p.error and "ZeroDivisionError" in p.error, p.error)
    p = programs.start(name="teimoso", code="import time\nwhile True:\n    time.sleep(0.01)\n")
    res = programs.stop("teimoso", wait_ms=300)
    conferir("programa sem delay() é avisado como travado", res["stuck"] == ["teimoso"], res)
    p.stop_flag = True  # (não dá para matar a thread; o teste só confere o aviso)

    # --- ferramentas: proteção dos arquivos do sistema, habilidades e memória ---
    r = await tools.call("write_file", {"path": "/core/agent.py", "content": "x"})
    conferir("write_file recusa /core", r.startswith("error"), r)
    r = await tools.call("write_file", {"path": "/skills/soma.py", "content": '"""Soma dois números."""\ndef soma(a, b):\n    return a + b\n'})
    conferir("write_file grava em /skills", r.startswith("saved"), r)
    conferir("índice das habilidades lê a docstring", ("soma", "Soma dois números.") in tools.skills_index(), tools.skills_index())
    sys.path.insert(0, os.path.join(TMP, "skills"))
    r = await tools.call("run_code", {"code": "import soma\nprint(soma.soma(2, 3))"})
    conferir("código importa a habilidade criada", "\n5" in r, r)
    await tools.call("write_file", {"path": "/skills/soma.py", "content": '"""Soma dois números."""\ndef soma(a, b):\n    return a + b + 100\n'})
    r = await tools.call("run_code", {"code": "import soma\nprint(soma.soma(2, 3))"})
    conferir("habilidade corrigida vale na hora (sem cache de import)", "\n105" in r, r)
    r = await tools.call("remember", {"note": "OLED is on SDA 9 / SCL 8"})
    conferir("remember entra no guia", r == "remembered" and "SDA 9" in agent.agent.guide())
    r = await tools.call("run_code", {"code": "import time\nwhile True:\n    delay(50)\n", "timeout_s": 1})
    conferir("run_code que não termina vira programa em segundo plano", "still running" in r, r)
    programs.stop("all")
    r = await tools.call("set_autostart", {"path": "/skills/soma.py", "enabled": True})
    conferir("autostart registra o arquivo", "/skills/soma.py" in r and config.get()["autostart"][0]["path"] == "/skills/soma.py", r)

    # --- API de arquivos ---
    st, r = await http(porta, "POST", "/api/file?path=/programs/teste.py", "print('oi')")
    st2, txt = await http(porta, "GET", "/api/file?path=/programs/teste.py", raw=True)
    st3, lst = await http(porta, "GET", "/api/files?path=/programs")
    conferir("API grava, lê e lista arquivos", txt == "print('oi')" and any(i["name"] == "teste.py" for i in lst["items"]), (st, txt, lst))

    # --- ESP-NOW: duas placas simuladas se descobrem, trocam texto e uma roda código na outra ---
    ar = Ar()
    mac_a, mac_b = b"\xaa" * 6, b"\xbb" * 6
    net.ESPNOW_FACTORY = lambda: FakeESPNow(ar, mac_a)
    net._st.update({"name": "placa-a", "channel": 6})
    net.start_espnow()
    b = segunda_placa()
    b.ESPNOW_FACTORY = lambda: FakeESPNow(ar, mac_b)
    b._st.update({"name": "placa-b", "channel": 6, "ip": "10.0.0.2"})
    b.start_espnow()
    ta, tb = asyncio.ensure_future(net.rx_loop()), asyncio.ensure_future(b.rx_loop())
    net.send_hello()
    await asyncio.sleep(0.3)
    conferir("as placas se descobrem (hello e resposta)", [p["name"] for p in net.peers_info()] == ["placa-b"] and [p["name"] for p in b.peers_info()] == ["placa-a"],
             (net.peers_info(), b.peers_info()))
    caixa = b.Inbox()
    r = await net.send_text("placa-b", "liga o LED " + "x" * 600)  # 3 pedaços
    await asyncio.sleep(0.3)
    msg = caixa.get(0)
    conferir("texto longo chega inteiro em pedaços", r == "sent" and msg and msg[0] == "placa-a" and msg[1].endswith("x" * 600) and len(msg[1]) == 611, (r, msg and len(msg[1])))
    r = await net.remote_run("placa-b", "print('rodei em', 'b')\nprint(sum(range(10)))", 5)
    conferir("uma placa roda código na outra e recebe a saída", "placa-b: status=done" in r and "rodei em b" in r and "45" in r, r)
    r = await net.send_text("ninguem", "oi")
    conferir("destino desconhecido dá erro claro", r.startswith("error: no board"), r)
    ta.cancel(); tb.cancel()

    srv.close()


asyncio.run(principal())
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d falha(s)" % falhas)
sys.exit(1 if falhas else 0)
