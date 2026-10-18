#!/usr/bin/env python3
"""Roda a página e a API no PC (Python comum), com o mesmo código da placa, para mexer na interface sem gravar nada.
Uso: python3 tools/dev_server.py [porta]   e abra http://127.0.0.1:8090
Sem modelo configurado, usa um modelo de mentira que chama run_code e responde com o resultado."""
import asyncio
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "board"))
sys.path.insert(0, os.path.join(ROOT, "board", "lib"))
from core import compat  # noqa: E402

compat.ROOT = tempfile.mkdtemp(prefix="otsp-dev-")
os.system(sys.executable + " " + os.path.join(ROOT, "tools", "build_web.py"))
shutil.copytree(os.path.join(ROOT, "board", "www"), os.path.join(compat.ROOT, "www"))
from core import config  # noqa: E402
from core.api import make_server  # noqa: E402


async def fake_model(reader, writer):
    await reader.readline()
    n = 0
    while True:
        h = await reader.readline()
        if h in (b"\r\n", b""):
            break
        if h.lower().startswith(b"content-length:"):
            n = int(h.split(b":")[1])
    body = json.loads(await reader.readexactly(n)) if n else {}
    tool_msgs = [m for m in body.get("messages", []) if m["role"] == "tool"]
    if not tool_msgs:
        msg = {"role": "assistant", "content": "Let me check with a quick program.", "tool_calls": [{"id": "c1", "type": "function",
               "function": {"name": "run_code", "arguments": json.dumps({"code": "for i in range(3):\n    print('tick', i)\n    delay(100)"})}}]}
    else:
        msg = {"role": "assistant", "content": "Done. The program printed:\n\n```\n" + tool_msgs[-1]["content"] + "\n```\n\nIt took **0.3 s**."}
    payload = json.dumps({"choices": [{"message": msg}]}).encode()
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(payload) + payload)
    await writer.drain()
    writer.close()


async def main(port):
    config.load()
    srv = await asyncio.start_server(fake_model, "127.0.0.1", 0)
    config.save({"llm_preset": "custom", "llm_base_url": "http://127.0.0.1:%d/v1" % srv.sockets[0].getsockname()[1], "llm_model": "fake"})
    await make_server().start("127.0.0.1", port)
    print("http://127.0.0.1:%d" % port)
    while True:
        await asyncio.sleep(3600)


asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8090))
