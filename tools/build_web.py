#!/usr/bin/env python3
"""Copia web/ para board/www/, comprimindo em gzip o que é texto (a placa manda o .gz com Content-Encoding: gzip)."""
import gzip
import hashlib
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, DST = os.path.join(ROOT, "web"), os.path.join(ROOT, "board", "www")
TEXT = (".html", ".js", ".css", ".svg", ".webmanifest", ".txt")


def versioned(html):
    """app.css e app.js ficam em cache por um dia no navegador: o ?v=<hash> força o arquivo novo depois de cada mudança."""
    for name in ("app.css", "app.js"):
        with open(os.path.join(SRC, name), "rb") as f:
            h = hashlib.sha1(f.read()).hexdigest()[:8]
        html = html.replace(('"%s"' % name).encode(), ('"%s?v=%s"' % (name, h)).encode())
    return html


def main():
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    total = 0
    for base, _, files in os.walk(SRC):
        for f in files:
            src = os.path.join(base, f)
            rel = os.path.relpath(src, SRC)
            dst = os.path.join(DST, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if f.endswith(TEXT):
                with open(src, "rb") as a:
                    data = a.read()
                if f == "index.html":
                    data = versioned(data)
                with open(dst + ".gz", "wb") as b:
                    b.write(gzip.compress(data, compresslevel=9, mtime=0))  # mtime fixo: o mesmo arquivo gera o mesmo .gz
                total += os.path.getsize(dst + ".gz")
            else:
                shutil.copy(src, dst)
                total += os.path.getsize(dst)
    shutil.copy(os.path.join(ROOT, "pc", "bridge.py"), os.path.join(DST, "bridge.py"))  # a placa entrega a ponte: curl http://<placa>/bridge.py
    print("board/www: %.1f KB" % (total / 1024))


if __name__ == "__main__":
    main()
