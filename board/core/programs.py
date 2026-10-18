# Programas: código Python que o agente (ou a pessoa) escreve e roda numa thread própria, para o servidor web
# continuar respondendo. Parar é cooperativo: os programas chamam delay(ms), que levanta StopProgram quando pedem parada.
import _thread
import sys
from . import compat, events

MAX_LOG = 200          # linhas guardadas por programa
MAX_RUNNING = 4


class StopProgram(Exception):
    pass


class Program:
    def __init__(self, name, path, code, args):
        self.name, self.path, self.code, self.args = name, path, code, args or {}
        self.status = "starting"      # starting, running, done, error, stopped
        self.log = []
        self.error = ""
        self.stop_flag = False
        self.started = compat.ticks_ms()
        self.ended = None
        self.lock = _thread.allocate_lock()

    def write(self, text):
        with self.lock:
            for line in str(text).split("\n"):
                self.log.append(line)
            if len(self.log) > MAX_LOG:
                del self.log[: len(self.log) - MAX_LOG]
        events.emit("program_output", name=self.name, text=str(text)[:500])

    def info(self):
        return {"name": self.name, "path": self.path, "status": self.status, "error": self.error[-600:],
                "runtime_ms": compat.ticks_diff(self.ended or compat.ticks_ms(), self.started), "log_lines": len(self.log)}


_programs = {}
_counter = [0]


def _forget_user_modules():
    # módulos de /skills e /programs são relidos a cada execução: assim um arquivo corrigido vale na hora
    for name in list(sys.modules.keys()):
        mod = sys.modules[name]
        f = getattr(mod, "__file__", "") or ""
        if "/skills/" in f or "/programs/" in f:
            del sys.modules[name]


def _namespace(prog):
    def p(*a, **k):
        prog.write(k.get("sep", " ").join(str(x) for x in a))

    def delay(ms):
        end = compat.ticks_ms() + int(ms)
        while True:
            if prog.stop_flag:
                raise StopProgram()
            left = compat.ticks_diff(end, compat.ticks_ms())
            if left <= 0:
                return
            compat.sleep_ms(min(left, 20))

    def should_stop():
        return prog.stop_flag

    return {"__name__": "__main__", "print": p, "delay": delay, "sleep_ms": delay, "should_stop": should_stop,
            "args": prog.args, "PROGRAM_NAME": prog.name}


def _run(prog):
    prog.status = "running"
    events.emit("program", name=prog.name, status="running")
    try:
        _forget_user_modules()
        code = compile(prog.code, prog.path or ("<" + prog.name + ">"), "exec")
        exec(code, _namespace(prog))
        prog.status = "done"
    except StopProgram:
        prog.status = "stopped"
    except BaseException as e:  # o programa errou: guarda o traceback para o agente corrigir
        if prog.stop_flag:
            prog.status = "stopped"
        else:
            prog.error = compat.format_exc(e)
            prog.write(prog.error)
            prog.status = "error"  # só depois de gravar: quem espera o fim (run_code) lê a saída já com o traceback
    prog.ended = compat.ticks_ms()
    events.emit("program", name=prog.name, status=prog.status, error=prog.error[-600:])


def start(name=None, code=None, path=None, args=None):
    running = [p for p in _programs.values() if p.status in ("starting", "running")]
    if name and name in _programs and _programs[name].status in ("starting", "running"):
        raise ValueError("program '%s' is already running; stop it first" % name)
    if len(running) >= MAX_RUNNING:
        raise ValueError("too many programs running (%d); stop one first" % len(running))
    if code is None:
        if not path:
            raise ValueError("give code or path")
        code = compat.read_text(path)
        if code is None:
            raise ValueError("file not found: " + path)
    if not name:
        _counter[0] += 1
        name = "run-%d" % _counter[0]
    prog = Program(name, path, code, args)
    _programs[name] = prog
    _old = [k for k, v in _programs.items() if v.status not in ("starting", "running")]
    for k in _old[:-10]:  # guarda só os 10 últimos terminados
        del _programs[k]
    try:
        _thread.stack_size(16 * 1024)
    except Exception:
        pass
    _thread.start_new_thread(_run, (prog,))
    return prog


def get(name):
    return _programs.get(name)


def all_info():
    return [p.info() for p in _programs.values()]


def stop(name="all", wait_ms=3000):
    targets = [p for p in _programs.values() if p.status in ("starting", "running") and (name in ("all", p.name))]
    for p in targets:
        p.stop_flag = True
    end = compat.ticks_ms() + wait_ms
    while any(p.status in ("starting", "running") for p in targets) and compat.ticks_diff(end, compat.ticks_ms()) > 0:
        compat.sleep_ms(20)
    stuck = [p.name for p in targets if p.status in ("starting", "running")]
    return {"stopped": [p.name for p in targets if p.name not in stuck], "stuck": stuck}


def wait(prog, timeout_ms):
    end = compat.ticks_ms() + timeout_ms
    while prog.status in ("starting", "running") and compat.ticks_diff(end, compat.ticks_ms()) > 0:
        compat.sleep_ms(20)
    return prog.status not in ("starting", "running")


async def await_done(prog, timeout_ms):
    import asyncio
    end = compat.ticks_ms() + timeout_ms
    while prog.status in ("starting", "running") and compat.ticks_diff(end, compat.ticks_ms()) > 0:
        await asyncio.sleep(0.05)
    return prog.status not in ("starting", "running")
