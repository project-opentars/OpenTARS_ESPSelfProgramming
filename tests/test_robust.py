#!/usr/bin/env python3
"""Robustez do agente com modelos fracos (o caso do gpt-oss na Groq): código despejado na resposta, chamadas de ferramenta tortas,
limite de uso, tool_use_failed, programas com o mesmo nome. Usa um modelo de mentira com roteiro. Uso: python3 tests/test_robust.py"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "board"))
sys.path.insert(0, os.path.join(RAIZ, "board", "lib"))

from core import compat  # noqa: E402

TMP = tempfile.mkdtemp(prefix="otsp-r-")
compat.ROOT = TMP
shutil.copytree(os.path.join(RAIZ, "board", "lib"), os.path.join(TMP, "lib"))

from core import agent as agent_mod, config, events, llm, programs, tools  # noqa: E402
from core.api import make_server  # noqa: E402

llm.WAIT_SCALE = 0.01  # os testes não esperam os segundos de verdade
falhas = 0


def conferir(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else "\n     " + str(detalhe)[:700])
    if not ok:
        falhas += 1


# ---------------- modelo de mentira com roteiro ----------------
ROTEIRO = []     # lista de funções(body) -> (status, headers_extra, corpo_json_ou_texto)
VISTO = []       # corpos recebidos


def tool_call(name, args, cid="c1", raw=False):
    return {"role": "assistant", "content": None, "tool_calls": [{"id": cid, "type": "function",
            "function": {"name": name, "arguments": args if raw else json.dumps(args)}}]}


def texto(t):
    return {"role": "assistant", "content": t}


async def servidor(reader, writer):
    await reader.readline()
    n, ra = 0, None
    while True:
        h = await reader.readline()
        if h in (b"\r\n", b""):
            break
        if h.lower().startswith(b"content-length:"):
            n = int(h.split(b":")[1])
    body = json.loads(await reader.readexactly(n)) if n else {}
    VISTO.append(body)
    status, extra, resp = ROTEIRO.pop(0)(body) if ROTEIRO else (200, "", {"choices": [{"message": texto("(sem roteiro)")}]})
    payload = (json.dumps(resp) if not isinstance(resp, (bytes, str)) else resp)
    payload = payload.encode() if isinstance(payload, str) else payload
    writer.write(b"HTTP/1.1 %d X\r\n%sContent-Length: %d\r\n\r\n" % (status, extra.encode(), len(payload)) + payload)
    await writer.drain()
    writer.close()


def ok(msg):
    return lambda body: (200, "", {"choices": [{"message": msg}]})


def falha(status, corpo, extra=""):
    return lambda body: (status, extra, corpo)


async def pedido(ag, texto_usuario):
    VISTO.clear()
    last = events.last_id()
    await ag.run(texto_usuario)
    return [e for e in events.since(last)]


async def principal():
    srv = await asyncio.start_server(servidor, "127.0.0.1", 0)
    porta = srv.sockets[0].getsockname()[1]
    config.load()
    config.save({"llm_base_url": "http://127.0.0.1:%d/v1" % porta, "llm_model": "fake", "llm_preset": "custom"})
    ag = agent_mod.Agent()
    CODIGO = "```python\nimport tars\nwhile not should_stop():\n    tars.led(0, 0, 40)\n    delay(100)\n```"

    # 1) código despejado na resposta: a harness cutuca e o modelo então roda
    ROTEIRO[:] = [ok(texto("Salve isto e rode:\n" + CODIGO)),
                  ok(tool_call("start_program", {"name": "pisca", "code": "while not should_stop():\n    delay(50)\n"})),
                  ok(texto("Pronto, está rodando."))]
    evs = await pedido(ag, "faça o led acender")
    txts = [e["text"] for e in evs if e["kind"] == "assistant"]
    conferir("código despejado leva uma cutucada e o modelo passa a rodar", programs.get("pisca") is not None and programs.get("pisca").status == "running", (txts, [e["kind"] for e in evs]))
    conferir("o despejo de código não aparece para o usuário", txts == ["Pronto, está rodando."], txts)
    conferir("a cutucada é uma mensagem [auto] e some do histórico da página",
             any(m["role"] == "user" and m["content"].startswith("[auto]") for m in ag.history), ag.history[:4])
    st = await make_server().routes[("GET", "/api/chat/history")](None)
    itens = json.loads(st[2])["items"]
    conferir("a página não vê as mensagens [auto]", not any("[auto]" in str(i.get("text", "")) for i in itens), itens)
    programs.stop("all")

    # 2) o modelo só mostra o código porque o usuário pediu para ver: depois de 2 cutucadas a resposta aparece
    ROTEIRO[:] = [ok(texto(CODIGO)), ok(texto(CODIGO)), ok(texto(CODIGO + " (não rodei)"))]
    evs = await pedido(ag, "mostre o código")
    txts = [e["text"] for e in evs if e["kind"] == "assistant"]
    conferir("sem tentar rodar, a resposta com código aparece depois de 2 cutucadas", len(txts) == 1 and "não rodei" in txts[0], txts)

    # 3) nomes tortos: "functions.run_code" e "default_api:run_code"
    ROTEIRO[:] = [ok(tool_call("functions.run_code", {"code": "print('a')"})), ok(tool_call("default_api:run_code", {"code": "print('b')"}, "c2")), ok(texto("feito"))]
    evs = await pedido(ag, "teste")
    res = [e["text"] for e in evs if e["kind"] == "tool_result"]
    conferir("prefixos no nome da ferramenta são aceitos", len(res) == 2 and "\na" in res[0] and "\nb" in res[1], res)

    # 4) argumentos cortados: o JSON é consertado; o inválido de verdade volta como erro claro
    ROTEIRO[:] = [ok(tool_call("run_code", '{"code": "print(7)"', raw=True)), ok(texto("ok"))]
    evs = await pedido(ag, "teste")
    res = [e["text"] for e in evs if e["kind"] == "tool_result"]
    conferir("JSON cortado (faltou a chave) é consertado", res and "\n7" in res[0], res)
    ROTEIRO[:] = [ok(tool_call("run_code", "isto nao e json", raw=True)), ok(tool_call("run_code", {"code": "print(8)"}, "c2")), ok(texto("ok"))]
    evs = await pedido(ag, "teste")
    res = [e["text"] for e in evs if e["kind"] == "tool_result"]
    conferir("JSON inválido volta como erro e o modelo reenvia", "not valid JSON" in res[0] and "\n8" in res[1], res)

    # 5) ferramenta que não existe: o erro lista as que existem
    ROTEIRO[:] = [ok(tool_call("browser_open", {"url": "x"})), ok(texto("ok"))]
    evs = await pedido(ag, "teste")
    res = [e["text"] for e in evs if e["kind"] == "tool_result"]
    conferir("ferramenta inexistente lista as válidas", "no tool called 'browser_open'" in res[0] and "run_code" in res[0], res)

    # 6) limite de uso (429) com Retry-After: espera e repete; sem sucesso, a mensagem explica
    ROTEIRO[:] = [falha(429, {"error": {"message": "rate limit"}}, "Retry-After: 7\r\n"), ok(texto("depois do limite"))]
    t0 = time.time()
    evs = await pedido(ag, "teste")
    conferir("429 com Retry-After repete e responde", [e["text"] for e in evs if e["kind"] == "assistant"] == ["depois do limite"]
             and any("model busy (HTTP 429)" in str(e.get("text")) and "in 8 s" in str(e.get("text")) for e in evs), [e.get("text") for e in evs])
    ROTEIRO[:] = [falha(429, "x")] * 5
    evs = await pedido(ag, "teste")
    err = [e["text"] for e in evs if e["kind"] == "error"]
    conferir("429 sem sucesso dá uma explicação útil", err and "rate limit" in err[0] and "Settings" in err[0], err)
    conferir("o pedido que falhou não deixa chamada de ferramenta órfã", ag.history[-1]["role"] == "user" and not ag.history[-1]["content"].startswith("[auto]"), ag.history[-2:])

    # 7) tool_use_failed da Groq: repete e funciona
    ROTEIRO[:] = [falha(400, {"error": {"message": "Failed to call a function", "code": "tool_use_failed"}}), ok(texto("agora foi"))]
    evs = await pedido(ag, "teste")
    conferir("tool_use_failed é repetido", [e["text"] for e in evs if e["kind"] == "assistant"] == ["agora foi"], [e.get("text") for e in evs])
    ROTEIRO[:] = [falha(400, {"error": {"message": "bad request"}})]
    evs = await pedido(ag, "teste")
    conferir("400 comum não é repetido", len(VISTO) == 1 and any(e["kind"] == "error" for e in evs), len(VISTO))

    # 7b) o código do erro vem depois de uma geração longa (passa dos 600 primeiros caracteres): ainda assim repete
    longo = '{"error":{"message":"Parsing failed. The model generated output that could not be parsed.","failed_generation":"' + "x" * 900 + '","code":"tool_use_failed"}}'
    ROTEIRO[:] = [falha(400, longo), ok(texto("depois do parse falho"))]
    evs = await pedido(ag, "teste")
    conferir("400 'Parsing failed' com o código no fim do corpo é repetido", [e["text"] for e in evs if e["kind"] == "assistant"] == ["depois do parse falho"], [e.get("text") for e in evs][:4])

    # 7c) resposta vazia: pede um resumo; se continuar vazia, mostra o último resultado
    ROTEIRO[:] = [ok(tool_call("run_code", {"code": "print('valor 99')"})), ok(texto("")), ok(texto("Rodei e imprimiu valor 99."))]
    evs = await pedido(ag, "teste vazio")
    conferir("resposta vazia leva um pedido de resumo e a resposta aparece", [e["text"] for e in evs if e["kind"] == "assistant"] == ["Rodei e imprimiu valor 99."], [e.get("text") for e in evs])
    ROTEIRO[:] = [ok(tool_call("run_code", {"code": "print('valor 77')"})), ok(texto("")), ok(texto("  ")), ok(texto(""))]
    evs = await pedido(ag, "teste vazio de novo")
    fin = [e["text"] for e in evs if e["kind"] == "assistant"]
    conferir("resposta vazia insistente mostra o último resultado da ferramenta", len(fin) == 1 and "valor 77" in fin[0], fin)

    # 8) esperas: o texto do provedor e o cabeçalho
    conferir("espera lida do cabeçalho", llm.retry_wait({"retry-after": "12"}, "", 1) == 13)
    conferir("espera lida do texto (Groq): 7.2s", llm.retry_wait({}, '... Please try again in 7.2s. Need more tokens?', 1) == 8)
    conferir("espera lida do texto (Groq): 1m4.5s", llm.retry_wait({}, "try again in 1m4.5s", 1) == 45)  # limitada a 45 s
    conferir("sem dica: 4 s por tentativa", llm.retry_wait({}, "", 2) == 9)

    # 9) mensagens de usuário seguidas (pedido que falhou) viram uma só para o provedor
    msgs = llm.clean_messages([{"role": "system", "content": "s"}, {"role": "user", "content": "um"}, {"role": "user", "content": "dois"}], "http://x")
    conferir("usuários seguidos são fundidos", [m["role"] for m in msgs] == ["system", "user"] and "um\ndois" == msgs[1]["content"], msgs)

    # 10) histórico: resultados antigos de ferramenta são encurtados e campos extras do provedor não ficam
    ag2 = agent_mod.Agent()
    ag2.history = []
    for i in range(8):
        ag2.history += [{"role": "user", "content": "u%d" % i}, tool_call("run_code", {"code": "x"}, "c%d" % i), {"role": "tool", "tool_call_id": "c%d" % i, "content": "R" * 2000}]
    ag2._shrink()
    tam = [len(m["content"]) for m in ag2.history if m["role"] == "tool"]
    conferir("resultados de ferramenta antigos são encurtados (os 4 mais novos ficam)", tam[-1] == 2000 and tam[0] < 500, tam)
    ROTEIRO[:] = [ok({"role": "assistant", "content": "oi", "reasoning": "pensamento longo " * 50})]
    await pedido(ag, "teste")
    conferir("campos extras (reasoning) não vão para o histórico", "reasoning" not in json.dumps(ag.history[-1]), ag.history[-1])

    # 10b) código antigo nas chamadas fica curto, mas continua sendo JSON válido; as 2 chamadas mais novas ficam inteiras
    ag4 = agent_mod.Agent()
    ag4.history = []
    for i in range(5):
        ag4.history += [{"role": "user", "content": "u%d" % i}, tool_call("write_file", {"path": "/skills/a.py", "content": "x = 1\n" * 200}, "c%d" % i),
                        {"role": "tool", "tool_call_id": "c%d" % i, "content": "saved"}]
    ag4._shrink()
    calls = [m for m in ag4.history if m.get("tool_calls")]
    tam = [len(json.loads(m["tool_calls"][0]["function"]["arguments"])["content"]) for m in calls]
    conferir("código antigo nas chamadas é encurtado e segue sendo JSON válido (as 2 mais novas ficam inteiras)", tam[0] < 300 and tam[-1] == 1200 and tam[-2] == 1200, tam)
    conferir("board_info é pequeno", len(json.dumps(tools.board_info())) < 600, len(json.dumps(tools.board_info())))

    # 11) start_program com o mesmo nome substitui o que está rodando
    r1 = await tools.call("start_program", {"name": "relogio", "code": "while not should_stop():\n    delay(20)\n"})
    r2 = await tools.call("start_program", {"name": "relogio", "code": "print('v2')\nwhile not should_stop():\n    delay(20)\n"})
    conferir("start_program com o mesmo nome troca a versão (não dá erro)", "replaced the running 'relogio'" in r2 and "v2" in r2 and "already running" not in r2, (r1, r2))
    programs.stop("all")

    # 12) fuso horário
    r = await tools.call("set_timezone", {"hours": -3})
    conferir("set_timezone grava em minutos", "UTC-3" in r and config.get()["tz_offset_min"] == -180, r)
    r = await tools.call("set_timezone", {"hours": 40})
    conferir("set_timezone recusa valor absurdo", r.startswith("error"), r)
    import tars  # noqa: E402
    h_utc = time.gmtime()[3]
    conferir("tars.localtime() aplica o fuso", tars.localtime()[3] == (h_utc - 3) % 24, (tars.localtime(), h_utc))
    conferir("o prompt informa o fuso", '"utc_offset_hours": -3.0' in ag.system_prompt(), "")
    conferir("o prompt manda rodar em vez de entregar código", "Never put a program in a reply" in ag.system_prompt())

    # 12b) o padrão antigo de max_tokens (4096) é migrado
    compat.write_text(config.PATH, json.dumps({"llm_max_tokens": 4096, "llm_model": "x"}))
    c = config.load()
    conferir("config antiga com max_tokens 4096 migra para o padrão novo", c["llm_max_tokens"] == 1500 and json.loads(compat.read_text(config.PATH))["llm_max_tokens"] == 1500, c["llm_max_tokens"])
    compat.write_text(config.PATH, json.dumps({"llm_base_url": "http://127.0.0.1:%d/v1" % porta, "llm_model": "fake", "llm_preset": "custom"}))
    config.load()

    # 13) histórico salvo com chamada de ferramenta sem resposta (queda no meio do pedido) é consertado ao ligar
    compat.write_text(agent_mod.HISTORY, json.dumps([{"role": "user", "content": "oi"}, tool_call("run_code", {"code": "x"})]))
    ag3 = agent_mod.Agent()
    conferir("histórico com chamada órfã é cortado ao carregar", ag3.history == [{"role": "user", "content": "oi"}], ag3.history)

    # 14) "pare" é tratado sem chamar o modelo
    p = programs.start(name="laco2", code="while not should_stop():\n    delay(20)\n")
    await asyncio.sleep(0.2)
    ROTEIRO[:] = []
    evs = await pedido(ag, "pare tudo!")
    conferir("'pare tudo' para os programas sem chamar o modelo", len(VISTO) == 0 and p.status == "stopped", (len(VISTO), p.status))
    conferir("e responde em português", [e["text"] for e in evs if e["kind"] == "assistant"] == ["Parei 1 programa(s)."], [e.get("text") for e in evs])
    evs = await pedido(ag, "Stop all the code")
    conferir("'Stop all the code' responde em inglês, sem programa rodando", [e["text"] for e in evs if e["kind"] == "assistant"] == ["No program was running."] and len(VISTO) == 0, [e.get("text") for e in evs])
    ROTEIRO[:] = [ok(texto("não é um comando de parar"))]
    evs = await pedido(ag, "pare isso e mostre o ip no display")
    conferir("frase maior que começa com 'pare' vai para o modelo", len(VISTO) == 1, len(VISTO))

    # 15) ler /lib devolve o resumo da API, não o arquivo todo
    r = await tools.call("read_file", {"path": "/lib/gfx.py"})
    conferir("read_file de /lib devolve o resumo (docstring + defs)", "def wire" in r and "summary of the API" in r and len(r) < 1600, (len(r), r[:200]))
    compat.write_text("/programs/x.py", "a = 1\n" * 400)
    r = await tools.call("read_file", {"path": "/programs/x.py"})
    conferir("read_file fora de /lib continua devolvendo o arquivo", r.startswith("a = 1") and len(r) > 1500, len(r))
    r = await tools.call("read_file", {"path": "lib/tars.py"})
    conferir("caminho sem a barra inicial também funciona", "def led" in r, r[:120])

    # 16) ritmo pela cota: aprende o limite do 429 e passa a esperar antes de estourar
    config.save({"llm_tpm": 0, "llm_max_tokens": 1500})
    ROTEIRO[:] = [falha(429, '{"error":{"message":"Rate limit reached for model in organization on tokens per minute (TPM): Limit 8000, Used 7000, Requested 2000. Please try again in 1.5s."}}'),
                  ok(texto("passou"))]
    evs = await pedido(ag, "teste de cota")
    conferir("o limite por minuto é aprendido do texto do 429 (85 %)", config.get()["llm_tpm"] == 6800, config.get()["llm_tpm"])
    llm._used[:] = [(compat.ticks_ms() - 5000, 6700)]   # já gastou 6700 tokens há 5 s
    ROTEIRO[:] = [ok(texto("depois da espera"))]
    evs = await pedido(ag, "outro teste")
    conferir("antes de passar da cota ele espera (e avisa)", any("waiting" in str(e.get("text")) and "token limit" in str(e.get("text")) for e in evs), [e.get("text") for e in evs])
    llm._used[:] = []
    ROTEIRO[:] = [ok(texto("sem espera"))]
    evs = await pedido(ag, "mais um")
    conferir("com a cota livre não espera", not any("waiting" in str(e.get("text")) for e in evs), [e.get("text") for e in evs])
    # um 429 mesmo se segurando baixa o limite aprendido em 10 %
    config.save({"llm_tpm": 6800})
    ROTEIRO[:] = [falha(429, '{"error":{"message":"Limit 8000, Used 7900, Requested 500. Please try again in 1s."}}'), ok(texto("ok"))]
    await pedido(ag, "teste")
    conferir("429 mesmo com ritmo baixa o limite em 10 %", config.get()["llm_tpm"] == 6120, config.get()["llm_tpm"])
    config.save({"llm_tpm": 0})

    srv.close()


asyncio.run(principal())
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d falha(s)" % falhas)
sys.exit(1 if falhas else 0)
