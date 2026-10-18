#!/usr/bin/env python3
"""Roda a página e a API no PC (Python comum), com o mesmo código da placa, para mexer na interface sem gravar nada.
Uso: python3 tools/dev_server.py [porta]   e abra http://127.0.0.1:8090
Para conversar, rode também: python3 pc/bridge.py http://127.0.0.1:8090"""
import asyncio
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


async def main(port):
    config.load()
    await make_server().start("127.0.0.1", port)
    print("http://127.0.0.1:%d" % port)
    while True:
        await asyncio.sleep(3600)


asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8090))
