#!/usr/bin/env python3
"""openTARS Self-Programming no Linux: Raspberry Pi, Orange Pi e a maioria dos SBCs (ou qualquer PC com Linux).
É o mesmo código da placa ESP32, rodando no Python do sistema: a mesma página, a mesma ponte, e a IA roda Python e comandos do Linux.
Uso: python3 sbc/opentars_sbc.py   (porta 8080; OPENTARS_PORT muda, OPENTARS_HOME muda a pasta de dados)"""
import os
import runpy
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("OPENTARS_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share", "opentars-sp")

sys.path[:0] = [os.path.join(ROOT, "board"), os.path.join(ROOT, "board", "lib"), os.path.join(DATA, "skills")]
from core import compat  # noqa: E402

compat.ROOT = DATA   # "/data", "/skills", "/programs" da placa viram pastas aqui dentro
compat.PORT = int(os.environ.get("OPENTARS_PORT", "8080"))
for d in ("data/files", "skills", "programs"):
    os.makedirs(os.path.join(DATA, d), exist_ok=True)
if not os.path.isdir(os.path.join(ROOT, "board", "www")):
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "build_web.py")])
shutil.rmtree(os.path.join(DATA, "www"), ignore_errors=True)   # a página sempre da versão do código
shutil.copytree(os.path.join(ROOT, "board", "www"), os.path.join(DATA, "www"))
runpy.run_path(os.path.join(ROOT, "board", "main.py"), run_name="__main__")
