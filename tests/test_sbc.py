#!/usr/bin/env python3
"""board/lib/sbc.py com libgpiod v1 e v2 de mentira (os nomes seguem as APIs reais, conferidas na fonte da 1.6 e no gpiod 2.5).
Não testa um GPIO de verdade. Uso: python3 tests/test_sbc.py"""
import enum
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "board", "lib"))
import sbc  # noqa: E402

falhas = 0


def conferir(nome, ok, det=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else det)
    falhas += 0 if ok else 1


ESTADO = {}


def v2():
    m = types.ModuleType("gpiod")
    line = types.ModuleType("gpiod.line")
    line.Value = enum.Enum("Value", {"INACTIVE": 0, "ACTIVE": 1})
    line.Direction = enum.Enum("Direction", "AS_IS INPUT OUTPUT")
    line.Bias = enum.Enum("Bias", "AS_IS UNKNOWN DISABLED PULL_UP PULL_DOWN")

    class Chip:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get_info(self):
            return types.SimpleNamespace(num_lines=288 if self.path == "/dev/gpiochip0" else 64)

        def line_offset_from_id(self, name):
            if self.path == "/dev/gpiochip1" and name == "PC5":
                return 69
            raise OSError("not found")

    class Req:
        def __init__(self, path, offset, s):
            self.path, self.offset = path, offset
            ESTADO[(path, offset)] = s.output_value

        def set_value(self, off, v):
            ESTADO[(self.path, off)] = v

        def get_value(self, off):
            return ESTADO[(self.path, off)]

        def release(self):
            ESTADO["released"] = True

    m.Chip, m.line = Chip, line
    m.LineSettings = lambda **kw: types.SimpleNamespace(**kw)
    m.request_lines = lambda path, consumer, config: Req(path, *next(iter(config.items())))
    sys.modules["gpiod"], sys.modules["gpiod.line"] = m, line


def v1():
    m = types.ModuleType("gpiod")
    m.LINE_REQ_DIR_IN, m.LINE_REQ_DIR_OUT, m.LINE_REQ_FLAG_BIAS_PULL_UP = 1, 2, 32

    class Line:
        def __init__(self, chip, off):
            self.chip, self.off = chip, off

        def request(self, consumer, type, flags=0, default_val=0):
            ESTADO[("v1", self.off)] = default_val
            ESTADO["v1req"] = (type, flags)

        def set_value(self, v):
            ESTADO[("v1", self.off)] = v

        def get_value(self):
            return ESTADO[("v1", self.off)]

        def release(self):
            ESTADO["released"] = True

        def owner(self):
            return self.chip

        def offset(self):
            return self.off

    class Chip:
        def __init__(self, path):
            self.path = path

        def get_line(self, off):
            return Line(self, off)

        def name(self):
            return "gpiochip0"

        def close(self):
            pass

    m.Chip = Chip
    m.find_line = lambda name: Line(Chip("gpiochip0"), 69) if name == "PC5" else None
    sys.modules["gpiod"] = m
    sys.modules.pop("gpiod.line", None)


sbc.chips = lambda: ["/dev/gpiochip0", "/dev/gpiochip1"]

v2()
p = sbc.Pin("PC5", out=True)
conferir("v2: acha a linha pelo nome no segundo chip", (p.offset, ESTADO.get(("/dev/gpiochip1", 69))) == (69, sys.modules["gpiod.line"].Value.INACTIVE))
p.on()
conferir("v2: on/value", p.value() == 1)
p.toggle()
conferir("v2: toggle", p.value() == 0)
p.close()
conferir("v2: close libera", ESTADO.pop("released", False))
try:
    sbc.Pin("PZ9")
    conferir("v2: nome inexistente dá erro claro", False)
except ValueError as e:
    conferir("v2: nome inexistente dá erro claro", "sbc.lines()" in str(e), e)

p = sbc.Pin("PI1", out=True)
conferir("v2: sem nome no kernel, PI1 vira 8*32+1 no chip principal", (p.offset, p._req.path) == (257, "/dev/gpiochip0"), (p.offset, p._req.path))

v1()
p = sbc.Pin("PC5", out=True, value=1)
conferir("v1: acha pelo nome e já liga", p.offset == 69 and p.value() == 1)
p.off()
conferir("v1: off", p.value() == 0)
sbc.Pin(5, pull="up")
conferir("v1: entrada com pull-up", ESTADO["v1req"] == (1, 32), ESTADO["v1req"])

sys.modules.pop("gpiod", None)
sys.modules["gpiod"] = None   # import gpiod -> ImportError
try:
    sbc.Pin(1)
    conferir("sem libgpiod: diz como instalar", False)
except RuntimeError as e:
    conferir("sem libgpiod: diz como instalar", "apt install python3-libgpiod" in str(e), e)
i = sbc.info()
conferir("info: campos principais", all(k in i for k in ("model", "temp_c", "mem_mb", "gpio_chips", "i2c_buses")), i)

print("\n%d falha(s)" % falhas)
sys.exit(1 if falhas else 0)
