# O agente: conversa com o modelo, executa as ferramentas e repete até o modelo responder sem pedir ferramenta.
import json
from . import compat, config, events, llm, tools

HISTORY = "/data/chat.json"
MAX_HISTORY_CHARS = 30000

SYSTEM = """You are openTARS Self-Programming, an AI agent that LIVES INSIDE a small microcontroller board ({machine}) running MicroPython.
You talk to the user through a web page served by this board (often from a phone). Reply in the user's language, briefly.

You can PROGRAM this board yourself. Nothing is pre-built for most requests: you write MicroPython code, run it, read the output and the
error, fix it and run again. Never answer "I can't" or "there is no feature for that" before trying code. A first attempt failing is normal.

How to work:
- run_code: test small pieces and do one-off actions (returns what was printed and the error with its line number).
- start_program: anything that keeps running (animations, monitors, reacting to buttons or messages). Programs MUST call delay(ms)
  inside every loop (delay is predefined; it is how a program can be stopped). Use print() to report.
- When something works and could be reused, save it as a module in /skills/<name>.py with a one-line docstring at the top, then
  `import <name>` from later code. This is YOUR growing library; prefer reusing it. Current library: {skills}
- remember: store durable facts (wiring, what the user likes, what failed and why).
- You cannot see the board, the screen, the LEDs or hear sounds: say what you ran and what it printed, never that it "looks right".
- Hardware safety: pins are 3.3 V; never drive motors, relays or mains directly from a pin; avoid GPIO 19/20 (USB), 26-37 (flash/PSRAM),
  43/44 (serial console) and 0/3/45/46 (boot) for new wiring.

MicroPython on this board (ESP32-S3, 8 MB PSRAM): `from machine import Pin, I2C, PWM, ADC, UART, SoftI2C`, `import neopixel`, `import time`,
`import framebuf`, `import network`, `import espnow`, `import requests` (HTTP). Inside programs and run_code these are predefined:
delay(ms), should_stop(), print, args.
Helper modules in /lib (read them with read_file for details):
- `import tars`: tars.led(r, g, b) for the onboard RGB LED; tars.oled() returns a ready OLED (framebuf API: fill, pixel, line, rect,
  fill_rect, ellipse, text(str, x, y) with an 8x8 font = 16 characters x 8 lines on 128x64, show) or None if no screen answers;
  tars.send(to, text) sends to another board by name ('all' = every board); inbox = tars.inbox() then inbox.get(timeout_ms) returns
  (sender, text) or None (poll it inside your loop); tars.peers() lists boards online; tars.button() is the BOOT button (value()==0 pressed).
- `import gfx`: g = gfx.Gfx(tars.oled()); g.wire(gfx.CUBE, ax, ay, az, scale) 3D wireframe, g.plot(values, x, y, w, h), g.bar(...).
Board configuration: {board}
Facts you remembered: {notes}"""


class Agent:
    def __init__(self):
        self.busy = False
        self.cancel = False
        self.history = self._load()

    def _load(self):
        txt = compat.read_text(HISTORY)
        try:
            return json.loads(txt) if txt else []
        except ValueError:
            return []

    def _save(self):
        try:
            compat.write_text(HISTORY, json.dumps(self.history))
        except Exception:
            pass

    def clear(self):
        self.history = []
        self._save()

    def _trim(self):
        # corta do começo, sempre num pedido do usuário, para não separar uma chamada de ferramenta da sua resposta
        while len(json.dumps(self.history)) > MAX_HISTORY_CHARS:
            idx = [i for i, m in enumerate(self.history) if m["role"] == "user"]
            if len(idx) < 2:
                self.history = self.history[-1:]
                break
            self.history = self.history[idx[1]:]

    def system_prompt(self):
        cfg = config.get()
        info = tools.board_info()
        skills = ", ".join("%s (%s)" % (n, d) if d else n for n, d in tools.skills_index()) or "(empty: start building it)"
        board = {"oled": cfg.get("oled"), "rgb_led_pin": cfg.get("rgb_led_pin"), "boot_button_pin": 0,
                 "name": info["network"].get("name"), "ip": info["network"].get("ip"), "espnow_peers": info["peers"]}
        return SYSTEM.format(machine=info["machine"] or "ESP32-S3", skills=skills, board=json.dumps(board),
                             notes=(tools.notes().strip() or "(none yet)"))

    async def run(self, text):
        if self.busy:
            raise ValueError("busy")
        self.busy, self.cancel = True, False
        cfg = config.get()
        self.history.append({"role": "user", "content": text})
        events.emit("user", text=text)
        events.emit("state", state="thinking")
        try:
            for _ in range(int(cfg.get("agent_max_rounds", 12))):
                if self.cancel:
                    events.emit("assistant", text="(stopped)")
                    break
                self._trim()
                msgs = [{"role": "system", "content": self.system_prompt()}] + self.history
                msg = await llm.chat(cfg, msgs, tools.TOOLS)
                self.history.append(msg)
                if msg.get("content"):
                    events.emit("assistant", text=msg["content"])
                calls = msg.get("tool_calls") or []
                if not calls:
                    break
                events.emit("state", state="working")
                for tc in calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except ValueError:
                        args = {}
                    events.emit("tool_call", name=name, args=args)
                    try:
                        result = await tools.call(name, args)
                    except Exception as e:
                        result = "error: " + str(e)
                    events.emit("tool_result", name=name, text=str(result)[:3000])
                    self.history.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": str(result)})
                events.emit("state", state="thinking")
            else:
                events.emit("assistant", text="(stopped after %d rounds without a final answer)" % cfg.get("agent_max_rounds", 12))
            events.emit("state", state="done")
        except Exception as e:
            events.emit("error", text=str(e))
            events.emit("state", state="error")
            # um pedido que falhou sem resposta deixaria uma chamada de ferramenta órfã: tira até o último pedido do usuário
            while self.history and self.history[-1]["role"] != "user":
                self.history.pop()
        finally:
            self.busy = False
            self._save()


agent = Agent()
