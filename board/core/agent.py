# O agente: a placa não pensa. Ela guarda o pedido numa fila, a ponte (pc/bridge.py, no computador da pessoa) busca,
# entrega a um programa de IA que já está instalado lá (claude, codex, opencode, pi, grok, ollama) e devolve a resposta.
# O programa de IA age na placa pelas rotas /api/tool e /api/run, como qualquer cliente.
import asyncio
import json
from . import compat, config, events, tools

HISTORY = "/data/chat.json"
MAX_ITEMS = 60
BRIDGE_ALIVE_MS = 35000    # a ponte pergunta por trabalho a cada ~20 s: sem notícia por mais que isso, ela saiu
JOB_MAX_MS = 15 * 60 * 1000
RECENT = 6                 # quantas trocas anteriores o programa de IA recebe (ele começa sem memória a cada pedido)

GUIDE = """You are openTARS Self-Programming: the brain of a small board ({machine}) running MicroPython. The user talks to you from a web page served by the board. You act on the board with the tools below; you run on the user's computer.

YOU run the code. The user cannot: they only read your final reply. Never answer with a program for the user to copy or save. Write code, run it on the board, read the output or the error, fix it, run it again.

Rules:
- Programs must call delay(ms) inside every loop (predefined; it is how they can be stopped) and print() to report. Predefined: delay, should_stop, print, args.
- start_program replaces a program with the same name. "stop" means stop_program name=all.
- Reusable pieces: save as /skills/<name>.py with a one-line docstring at the top, then `import <name>`. Library now: {skills}
- remember: durable facts (wiring, preferences). Known now: {notes}
- You cannot see the board, screen or LEDs, or hear sounds: say what you ran and what it printed, never that it "looks right".
- Do not touch files on the computer: the board is the only thing you work on.
- Reply in the user's language, in one to three sentences. Pins are 3.3 V; never drive motors, relays or mains directly from a pin; avoid GPIO 19/20 (USB), 26-37 (flash/PSRAM), 43/44 (console), 0/3/45/46 (boot) for new wiring.

Available in MicroPython: machine (Pin, I2C, PWM, ADC, UART), neopixel, framebuf, network, espnow, requests, time, math, ntptime. Not available: inspect and most of CPython's standard library.
Helpers (read /lib/*.py with read_file for details):
- `import tars`: tars.led(r,g,b) onboard RGB LED; tars.oled() ready OLED (framebuf: fill, pixel, line, rect, fill_rect, ellipse, text(str,x,y) 8x8 font = 16 chars x 8 lines, show) or None; tars.button() BOOT button (value()==0 pressed); tars.send(to,text), inbox=tars.inbox(); inbox.get(timeout_ms) -> (sender,text) or None, tars.peers(); tars.localtime() / tars.now() the clock in the user's time zone (set_timezone tool).
- `import gfx`: g = gfx.Gfx(tars.oled()); g.wire(gfx.CUBE, ax, ay, az) 3D wireframe, g.plot, g.bar.
Board: {board}

Tools:
{tools}"""

STOP_PT = ("pare", "para", "parar", "pare tudo", "para tudo", "parar tudo", "pare isso", "para isso", "pare o programa", "cancela", "cancelar", "chega")
STOP_EN = ("stop", "stop all", "stop everything", "stop all the code", "stop it", "stop that", "stop the program", "halt", "cancel", "kill all")

NO_BRIDGE = ("No computer is connected. Open the page on your computer, go to Settings and copy the connect command.",
             "Nenhum computador conectado. Abra a página no computador, vá em Ajustes e copie o comando de conectar.")


def _stop_command(text):
    """'pare', 'stop all'...: tratado direto, sem acordar o programa de IA. Devolve 'pt', 'en' ou ''."""
    t = (text or "").lower().strip(" .!?,;:")
    return "pt" if t in STOP_PT else "en" if t in STOP_EN else ""


class Agent:
    def __init__(self):
        self.busy = False
        self.cancel = False
        self.job = None            # pedido esperando a ponte
        self.taken = False
        self.finished = None       # (ok, texto) quando a ponte terminou
        self.seen = None           # última vez que a ponte apareceu
        self.available = []        # programas de IA que a ponte achou no computador
        self.working = ""          # o que está rodando agora
        self._id = 0
        self.history = self._load()

    # ---- histórico (só para a página recarregar a conversa) ----
    def _load(self):
        txt = compat.read_text(HISTORY)
        try:
            h = json.loads(txt) if txt else []
        except ValueError:
            h = []
        return [i for i in h if isinstance(i, dict) and i.get("kind") in ("user", "assistant", "tool_call", "tool_result")] if isinstance(h, list) else []

    def _add(self, item):
        self.history.append(item)
        del self.history[:-MAX_ITEMS]

    def _save(self):
        try:
            compat.write_text(HISTORY, json.dumps(self.history))
        except Exception:
            pass

    def clear(self):
        self.history = []
        self._save()

    def note_tool(self, name, args, result):
        self._add({"kind": "tool_call", "name": name, "args": args})
        self._add({"kind": "tool_result", "text": str(result)[:1500]})

    # ---- ponte ----
    def connected(self):
        return self.seen is not None and compat.ticks_diff(compat.ticks_ms(), self.seen) < BRIDGE_ALIVE_MS

    async def poll(self, available):
        """A ponte pergunta por trabalho; a placa segura a resposta até 20 s."""
        self.available = [str(a)[:20] for a in available][:12]
        end = compat.ticks_ms() + 20000
        while compat.ticks_diff(end, compat.ticks_ms()) > 0:
            self.seen = compat.ticks_ms()
            if self.job and not self.taken:
                self.taken = True
                return self.job
            await asyncio.sleep(0.2)
        return None

    def bridge_event(self, job_id, kind, text):
        """Evento da ponte durante o trabalho. Devolve True quando a pessoa pediu para parar."""
        self.seen = compat.ticks_ms()
        if self.job and self.job["id"] == job_id and kind == "log" and text:
            self.working = text[:80]
            events.emit("log", text=text[:200])
        return self.cancel

    def bridge_done(self, job_id, ok, text):
        self.seen = compat.ticks_ms()
        if self.job and self.job["id"] == job_id:
            self.finished = (bool(ok), str(text or ""))

    # ---- contexto entregue ao programa de IA ----
    def guide(self):
        cfg = config.get()
        info = tools.board_info()
        skills = ", ".join("%s (%s)" % (n, d) if d else n for n, d in tools.skills_index()) or "(empty: start building it)"
        board = {"oled": cfg.get("oled"), "rgb_led_pin": cfg.get("rgb_led_pin"), "boot_button_pin": 0, "name": info["name"], "ip": info["ip"],
                 "espnow_peers": info["peers"], "utc_offset_hours": cfg.get("tz_offset_min", 0) / 60}
        lines = []
        for t in tools.TOOLS:
            f = t["function"]
            lines.append("- %s(%s): %s" % (f["name"], ", ".join(f["parameters"]["properties"]), f["description"]))
        return GUIDE.format(machine=info["machine"] or "ESP32-S3", skills=skills, board=json.dumps(board),
                            notes=(tools.notes().strip() or "(none yet)"), tools="\n".join(lines))

    def recent(self):
        out = [(i["kind"], i.get("text", "")) for i in self.history if i["kind"] in ("user", "assistant")]
        return [{"role": k, "text": t[:600]} for k, t in out[-RECENT - 1:-1]]   # sem o pedido de agora (é o último)

    # ---- um pedido ----
    async def run(self, text):
        if self.busy:
            raise ValueError("busy")
        self.busy, self.cancel = True, False
        cfg = config.get()
        pt = cfg.get("lang") == "pt"
        self._add({"kind": "user", "text": text})
        events.emit("user", text=text)
        try:
            stop = _stop_command(text)
            if stop:
                res = tools.programs.stop("all")
                n = len(res["stopped"])
                if res["stuck"]:
                    reply = ("Pedi para parar, mas %s não responde (o código não chama delay()). Reinicie a placa em Ajustes." if stop == "pt"
                             else "I asked %s to stop but it does not respond (its code never calls delay()). Restart the board in Settings.") % ", ".join(res["stuck"])
                elif stop == "pt":
                    reply = "Parei %d programa(s)." % n if n else "Não havia nenhum programa rodando."
                else:
                    reply = "Stopped %d program(s)." % n if n else "No program was running."
                events.emit("tool_call", name="stop_program", args={"name": "all"})
                events.emit("tool_result", name="stop_program", text=("stopped: " + ", ".join(res["stopped"])) if res["stopped"] else "nothing was running")
                self.note_tool("stop_program", {"name": "all"}, "stopped: " + ", ".join(res["stopped"]) if res["stopped"] else "nothing was running")
                self._add({"kind": "assistant", "text": reply})
                events.emit("assistant", text=reply)
                events.emit("state", state="done")
                return
            if not self.connected():
                self.history.pop()    # sem resposta, o pedido não fica: a pessoa manda de novo depois de conectar
                events.emit("error", text=NO_BRIDGE[1 if pt else 0], reason="no_bridge", detail="")
                events.emit("state", state="error")
                return
            self._id += 1
            self.finished, self.taken, self.working = None, False, ""
            self.job = {"id": self._id, "text": text, "guide": self.guide(), "recent": self.recent(),
                        "harness": cfg.get("harness", ""), "model": cfg.get("harness_model", "")}
            events.emit("state", state="thinking")
            start, cancelled_at = compat.ticks_ms(), None
            while self.finished is None:
                now = compat.ticks_ms()
                if not self.connected():
                    self.finished = (False, "The computer stopped answering." if not pt else "O computador parou de responder.")
                elif compat.ticks_diff(now, start) > JOB_MAX_MS:
                    self.finished = (False, "Took too long (15 min)." if not pt else "Demorou demais (15 min).")
                elif self.cancel:
                    cancelled_at = cancelled_at or now
                    if compat.ticks_diff(now, cancelled_at) > 8000:    # a ponte não confirmou a parada
                        self.finished = (False, "(stopped)")
                await asyncio.sleep(0.2)
            ok, reply = self.finished
            if ok and reply.strip():
                self._add({"kind": "assistant", "text": reply})
                events.emit("assistant", text=reply)
                events.emit("state", state="done")
            elif self.cancel:
                events.emit("assistant", text="(stopped)")
                events.emit("state", state="done")
            else:
                events.emit("error", text=reply or ("The AI program gave no answer." if not pt else "O programa de IA não respondeu."),
                            reason="harness", detail="")
                events.emit("state", state="error")
        finally:
            self.job = None
            self.busy = False
            self._save()


agent = Agent()
