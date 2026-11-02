#!/usr/bin/env python3
"""Monta o site (docs/, publicado pelo GitHub Pages): copia o sistema da placa e o firmware para o gravador do navegador.
O GitHub Pages serve o que está commitado, então docs/flasher/ é gerado aqui e vai junto no commit."""
import glob
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "flasher")


def main():
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_web.py")], check=True)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    # os mesmos arquivos que tools/deploy.sh copia: core, lib, www, main.py e boot.py
    files = []
    board = os.path.join(ROOT, "board")
    for base, dirs, names in os.walk(board):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for n in sorted(names):
            src = os.path.join(base, n)
            rel = os.path.relpath(src, board).replace(os.sep, "/")
            dst = os.path.join(OUT, "board", rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(src, dst)
            files.append({"path": rel, "size": os.path.getsize(src)})
    with open(os.path.join(OUT, "files.json"), "w") as f:
        json.dump(files, f, indent=0)
    bins = sorted(glob.glob(os.path.join(ROOT, "firmware", "*.bin")), key=os.path.getmtime)
    if not bins:
        sys.exit("falta o firmware em firmware/ (ESP32_GENERIC_S3-SPIRAM_OCT de micropython.org)")
    shutil.copy(bins[-1], os.path.join(OUT, "micropython.bin"))
    version = os.path.basename(bins[-1]).rsplit("-v", 1)[-1][:-4]
    manifest = {
        "name": "MicroPython %s for ESP32-S3 (octal PSRAM)" % version,
        "version": version,
        "new_install_prompt_erase": True,
        "builds": [{"chipFamily": "ESP32-S3", "parts": [{"path": "micropython.bin", "offset": 0}]}],
    }
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("docs/flasher: %d arquivos da placa (%.0f KB), MicroPython %s" % (
        len(files), sum(x["size"] for x in files) / 1024, version))


if __name__ == "__main__":
    main()
