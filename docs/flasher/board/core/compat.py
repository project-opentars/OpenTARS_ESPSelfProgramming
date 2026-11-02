# Diferenças entre MicroPython (na placa) e CPython (nos testes do PC), num lugar só.
import sys
import time

MICRO = sys.implementation.name == "micropython"

# Raiz do sistema de arquivos: "" na placa (caminhos "/x"); nos testes aponta para uma pasta temporária.
ROOT = ""


def fs(path):
    return ROOT + path


if MICRO:
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    sleep_ms = time.sleep_ms

    def format_exc(e):
        import io
        buf = io.StringIO()
        sys.print_exception(e, buf)
        return buf.getvalue()
else:
    _T0 = time.monotonic()

    def ticks_ms():
        return int((time.monotonic() - _T0) * 1000)

    def ticks_diff(a, b):
        return a - b

    def sleep_ms(ms):
        time.sleep(ms / 1000)

    def format_exc(e):
        import traceback
        return "".join(traceback.format_exception(type(e), e, e.__traceback__))


async def asleep_ms(ms):
    import asyncio
    await asyncio.sleep(ms / 1000)


def exists(path):
    import os
    try:
        os.stat(fs(path))
        return True
    except OSError:
        return False


def is_dir(path):
    import os
    try:
        return (os.stat(fs(path))[0] & 0x4000) != 0
    except OSError:
        return False


def makedirs(path):
    import os
    cur = ""
    for part in path.strip("/").split("/"):
        cur += "/" + part
        if not exists(cur):
            try:
                os.mkdir(fs(cur))
            except OSError:
                pass


def read_text(path, default=None):
    try:
        with open(fs(path)) as f:
            return f.read()
    except (OSError, UnicodeError, ValueError):  # não existe, é pasta, ou é binário
        return default


def write_text(path, text):
    folder = path.rsplit("/", 1)[0]
    if folder:
        makedirs(folder)
    tmp = path + ".tmp"
    with open(fs(tmp), "w") as f:  # grava num temporário e troca: uma queda de energia não deixa arquivo pela metade
        f.write(text)
    import os
    try:
        os.remove(fs(path))
    except OSError:
        pass
    os.rename(fs(tmp), fs(path))


def mem_info():
    try:
        import gc
        gc.collect()
        return {"free": gc.mem_free(), "used": gc.mem_alloc()}
    except AttributeError:
        return {"free": 0, "used": 0}
