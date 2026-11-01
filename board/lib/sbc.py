"""Linux boards (Raspberry Pi, Orange Pi and other SBCs): GPIO with libgpiod v1 or v2, and board info.
    import sbc
    led = sbc.Pin("PC5", out=True)        # by line name (see sbc.lines()) or sbc.Pin(69, chip="gpiochip0")
    led.on(); led.off(); led.toggle()
    btn = sbc.Pin("PC6", pull="up")      # input; btn.value() -> 0 or 1
    sbc.info()                           # model, temperature, memory, disk, gpio chips, i2c buses, permissions
"""
import glob
import os
import re

_HINT_GPIOD = "python3-libgpiod is not installed. Install it with: sudo apt install python3-libgpiod gpiod"


def _gpiod():
    try:
        import gpiod
        return gpiod
    except ImportError:
        raise RuntimeError(_HINT_GPIOD)


def _read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip("\x00\n ")
    except OSError:
        return default


def chips():
    return sorted(glob.glob("/dev/gpiochip*"), key=lambda p: int(p[13:] or 0))


def _find(name):
    """(caminho do chip, offset) da linha com esse nome, ou erro dizendo onde procurar."""
    gpiod = _gpiod()
    for path in chips():
        if hasattr(gpiod, "request_lines"):   # v2
            try:
                with gpiod.Chip(path) as c:
                    return path, c.line_offset_from_id(name)
            except (OSError, ValueError):
                continue
        else:                                 # v1
            line = gpiod.find_line(name)
            if line is not None:
                return "/dev/" + line.owner().name(), line.offset()
            break
    m = re.match(r"P([A-K])(\d{1,2})$", name)
    if m:   # Allwinner (Orange Pi, Banana Pi): offset = letra * 32 + número no controlador principal
        # shortcut: o principal é o chip com mais linhas (PA..PK); os pinos PL/PM ficam fora, use sbc.Pin(offset, chip=...)
        sizes = {}
        for path in chips():
            try:
                if hasattr(gpiod, "request_lines"):
                    with gpiod.Chip(path) as c:
                        sizes[path] = c.get_info().num_lines
                else:
                    c = gpiod.Chip(path)
                    sizes[path] = c.num_lines()
                    c.close()
            except OSError:
                continue
        if sizes:
            return max(sizes, key=sizes.get), (ord(m.group(1)) - 65) * 32 + int(m.group(2))
    raise ValueError("no GPIO line named %r. List them with sbc.lines() or `gpioinfo`" % name)


def lines():
    """{chip: [nomes das linhas]} (só as que têm nome). Precisa de permissão no /dev/gpiochip*."""
    gpiod = _gpiod()
    out = {}
    for path in chips():
        try:
            if hasattr(gpiod, "request_lines"):
                with gpiod.Chip(path) as c:
                    n = c.get_info().num_lines
                    out[path] = [c.get_line_info(i).name or str(i) for i in range(n)]
            else:
                c = gpiod.Chip(path)
                out[path] = [c.get_line(i).name() or str(i) for i in range(c.num_lines())]
                c.close()
        except OSError as e:
            out[path] = "error: %s" % e
    return out


class Pin:
    """Uma linha de GPIO. out=True: saída (value = valor inicial). pull: "up", "down" ou None (entrada)."""

    def __init__(self, line, chip=None, out=False, value=0, pull=None):
        gpiod = _gpiod()
        if isinstance(line, str) and not line.isdigit():
            path, offset = _find(line)
        else:
            path, offset = chip or (chips() or ["/dev/gpiochip0"])[0], int(line)
        if not path.startswith("/dev/"):
            path = "/dev/" + path
        self.out, self.offset = out, offset
        try:
            if hasattr(gpiod, "request_lines"):
                from gpiod.line import Bias, Direction, Value
                self._V = Value
                bias = {"up": Bias.PULL_UP, "down": Bias.PULL_DOWN}.get(pull, Bias.AS_IS)
                s = gpiod.LineSettings(direction=Direction.OUTPUT if out else Direction.INPUT, bias=bias,
                                       output_value=Value.ACTIVE if value else Value.INACTIVE)
                self._req = gpiod.request_lines(path, consumer="opentars", config={offset: s})
            else:
                self._V = None
                flags = {"up": getattr(gpiod, "LINE_REQ_FLAG_BIAS_PULL_UP", 0),
                         "down": getattr(gpiod, "LINE_REQ_FLAG_BIAS_PULL_DOWN", 0)}.get(pull, 0)
                self._chip = gpiod.Chip(path)
                self._req = self._chip.get_line(offset)
                self._req.request(consumer="opentars", type=gpiod.LINE_REQ_DIR_OUT if out else gpiod.LINE_REQ_DIR_IN,
                                  flags=flags, default_val=1 if value else 0)
        except PermissionError:
            raise RuntimeError("no permission to use %s. The user must run once, in the openTARS folder: "
                               "sbc/install.sh --hardware (uses sudo), then reboot the board." % path)
        except OSError as e:
            if getattr(e, "errno", 0) == 16:
                raise RuntimeError("GPIO line %s on %s is busy (used by the kernel or another program)" % (offset, path))
            raise

    def value(self, v=None):
        if v is None:
            if self._V:
                return 1 if self._req.get_value(self.offset) == self._V.ACTIVE else 0
            return self._req.get_value()
        if self._V:
            self._req.set_value(self.offset, self._V.ACTIVE if v else self._V.INACTIVE)
        else:
            self._req.set_value(1 if v else 0)

    def on(self):
        self.value(1)

    def off(self):
        self.value(0)

    def toggle(self):
        self.value(0 if self.value() else 1)

    def close(self):
        try:
            self._req.release()
        finally:
            if getattr(self, "_chip", None):
                self._chip.close()


def temp():
    """Temperatura mais alta dos sensores do sistema, em °C (None se não houver)."""
    vals = []
    for z in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            vals.append(int(_read(z)) / 1000)
        except ValueError:
            pass
    return max(vals) if vals else None


def info():
    mem = {}
    for ln in _read("/proc/meminfo").splitlines():
        k, _, v = ln.partition(":")
        mem[k] = int(v.split()[0]) // 1024 if v.split() else 0
    st = os.statvfs(os.path.expanduser("~"))
    gpio = chips()
    i2c = sorted(glob.glob("/dev/i2c-*"))
    try:
        import gpiod
        lib = "libgpiod v2" if hasattr(gpiod, "request_lines") else "libgpiod v1"
    except ImportError:
        lib = "not installed (" + _HINT_GPIOD + ")"
    return {
        "model": _read("/proc/device-tree/model") or os.uname().machine,
        "kernel": os.uname().release,
        "temp_c": temp(),
        "load": os.getloadavg(),
        "mem_mb": {"total": mem.get("MemTotal"), "available": mem.get("MemAvailable")},
        "disk_home_free_gb": round(st.f_bavail * st.f_frsize / 1e9, 1),
        "uptime_s": int(float((_read("/proc/uptime") or "0").split()[0])),
        "gpio_chips": {p: os.access(p, os.R_OK | os.W_OK) for p in gpio},   # True = este usuário pode usar
        "gpio_library": lib,
        "i2c_buses": {p: os.access(p, os.R_OK | os.W_OK) for p in i2c},
        "leds": sorted(os.path.basename(p) for p in glob.glob("/sys/class/leds/*")),
        "user": os.environ.get("USER", ""),
    }
