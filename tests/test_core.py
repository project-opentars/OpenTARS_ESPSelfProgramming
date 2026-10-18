#!/usr/bin/env python3
"""Testes do núcleo no Python do PC (sem a placa): servidor web, cliente HTTP, agente com um modelo de mentira,
programas em threads, ferramentas e duas "placas" ESP-NOW simuladas. Uso: python3 tests/test_core.py"""
import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "board"))
sys.path.insert(0, os.path.join(RAIZ, "board", "lib"))

from core import compat  # noqa: E402

TMP = tempfile.mkdtemp(prefix="otsp-")
compat.ROOT = TMP
shutil.copytree(os.path.join(RAIZ, "board", "www"), os.path.join(TMP, "www"))

from core import agent, config, events, http_client, llm, net, programs, tools, web  # noqa: E402
from core.api import make_server  # noqa: E402

falhas = 0


def conferir(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else "\n     " + str(detalhe)[:600])
    if not ok:
        falhas += 1


# ---------------- modelo de mentira (formato OpenAI) ----------------
PEDIDOS = []


def resposta_do_modelo(body):
    """Roteiro: 1º pedido -> chama run_code; depois do resultado -> responde com o que o código imprimiu."""
    msgs = body["messages"]
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    if not tool_msgs:
        return {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function",
                "extra_content": {"google": {"thought_signature": "abc"}},
                "function": {"name": "run_code", "arguments": json.dumps({"code": "x = 6 * 7\nprint('answer', x)"})}}]}
    return {"role": "assistant", "content": "The board printed: " + tool_msgs[-1]["content"].split("\n")[1]}


async def servidor_modelo(reader, writer):
    line = await reader.readline()
    headers = {}
    while True:
        h = await reader.readline()
        if h in (b"\r\n", b""):
            break
        k, _, v = h.decode().partition(":")
        headers[k.strip().lower()] = v.strip()
    body = json.loads(await reader.readexactly(int(headers.get("content-length", 0)))) if headers.get("content-length") else {}
    path = line.split()[1].decode()
    PEDIDOS.append({"path": path, "body": body, "auth": headers.get("authorization")})
    if path.endswith("/models"):
        payload = json.dumps({"data": [{"id": "models/gemini-x"}, {"id": "qwen3:4b"}]}).encode()
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(payload) + payload)
    else:
        payload = json.dumps({"choices": [{"message": resposta_do_modelo(body)}]}).encode()
        # resposta em pedaços (chunked), para exercitar esse caminho do cliente
        half = len(payload) // 2
        writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n")
        for part in (payload[:half], payload[half:]):
            writer.write(b"%x\r\n" % len(part) + part + b"\r\n")
        writer.write(b"0\r\n\r\n")
    await writer.drain()
    writer.close()


async def http(port, method, path, body=None, raw=False):
    status, _, data = await http_client.request(method, "http://127.0.0.1:%d%s" % (port, path),
                                                {"Content-Type": "application/json"} if body is not None else None,
                                                body if isinstance(body, str) or body is None else json.dumps(body), 20)
    return status, (data.decode() if raw else json.loads(data or b"{}"))


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
    srv_modelo = await asyncio.start_server(servidor_modelo, "127.0.0.1", 0)
    porta_modelo = srv_modelo.sockets[0].getsockname()[1]
    config.load()
    srv = await make_server().start("127.0.0.1", 0)
    porta = srv.sockets[0].getsockname()[1]

    # --- web: estático com gzip e 404 ---
    st, _, data = await http_client.request("GET", "http://127.0.0.1:%d/" % porta)
    conferir("página inicial servida (gzip)", st == 200 and data[:2] == b"\x1f\x8b", (st, data[:20]))
    st, _ = await http(porta, "GET", "/api/nada")
    conferir("rota inexistente dá 404", st == 404)
    conferir("unquote com %, + e acento", web.unquote("a%20b+c%C3%A9") == "a b cé", web.unquote("a%20b+c%C3%A9"))

    # --- config: chave mascarada não volta para o disco ---
    st, r = await http(porta, "POST", "/api/config", {"llm_base_url": "http://127.0.0.1:%d/v1" % porta_modelo, "llm_api_key": "segredo123",
                                                       "llm_model": "fake", "llm_preset": "custom"})
    conferir("config salva e mascara a chave", r["config"]["llm_api_key"].endswith("o123") and "segredo" not in json.dumps(r), r)
    await http(porta, "POST", "/api/config", {"llm_api_key": r["config"]["llm_api_key"]})
    conferir("chave mascarada enviada de volta não sobrescreve", config.get()["llm_api_key"] == "segredo123", config.get()["llm_api_key"])

    # --- modelos ---
    st, r = await http(porta, "GET", "/api/models")
    conferir("lista de modelos (tira o prefixo models/)", r.get("models") == ["gemini-x", "qwen3:4b"], r)

    # --- conversa de ponta a ponta: o modelo chama run_code e responde com o resultado ---
    PEDIDOS.clear()
    st, r = await http(porta, "POST", "/api/chat", {"text": "quanto é 6 vezes 7? rode na placa"})
    conferir("pedido aceito", st == 200, r)
    st, r = await http(porta, "POST", "/api/chat", {"text": "outro"})
    conferir("segundo pedido enquanto ocupado dá 409", st == 409, (st, r))
    vistos, last = [], 0
    for _ in range(100):
        st, r = await http(porta, "GET", "/api/events?since=%d" % last)
        for e in r["events"]:
            vistos.append(e)
            last = e["id"]
        if any(e["kind"] == "state" and e["state"] in ("done", "error") for e in vistos):
            break
        await asyncio.sleep(0.05)
    kinds = [e["kind"] for e in vistos]
    final = [e for e in vistos if e["kind"] == "assistant"]
    conferir("eventos: user, tool_call, tool_result, assistant", all(k in kinds for k in ("user", "tool_call", "tool_result", "assistant")), kinds)
    conferir("o código rodou na thread e voltou ao modelo", final and "answer 42" in final[-1]["text"], [e for e in vistos if e["kind"] in ("tool_result", "assistant", "error")])
    corpo = PEDIDOS[-1]["body"]
    conferir("pedido ao modelo leva as ferramentas e a chave", corpo.get("tools") and PEDIDOS[-1]["auth"] == "Bearer segredo123")
    conferir("extra_content não vai para provedor que não é o Gemini", "extra_content" not in json.dumps(corpo["messages"]), corpo["messages"])
    conferir("o prompt do sistema cita a placa e a biblioteca", "YOU run the code" in corpo["messages"][0]["content"])
    gem = llm.clean_messages(agent.agent.history, "https://generativelanguage.googleapis.com/v1beta/openai")
    conferir("extra_content volta quando o destino é o Gemini", "thought_signature" in json.dumps(gem))
    st, r = await http(porta, "GET", "/api/chat/history")
    conferir("histórico reconstrói a conversa", [i["kind"] for i in r["items"]][:2] == ["user", "tool_call"], r)

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
    conferir("remember entra no prompt", r == "remembered" and "SDA 9" in agent.agent.system_prompt())
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

    srv.close(); srv_modelo.close()


asyncio.run(principal())
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d falha(s)" % falhas)
sys.exit(1 if falhas else 0)
