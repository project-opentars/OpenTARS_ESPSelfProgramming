# O agente: conversa com o modelo, executa as ferramentas e repete até o modelo responder sem pedir ferramenta.
import json
from . import compat, config, events, llm, tools

HISTORY = "/data/chat.json"
MAX_HISTORY_CHARS = 24000
OLD_TOOL_RESULT = 300      # resultados de ferramenta antigos são encurtados: menos tokens por pedido (limites por minuto dos provedores)
KEEP_RECENT_TOOLS = 3
OLD_CODE = 220             # código de chamadas antigas (run_code, write_file...) também: o modelo só precisa do começo para lembrar
KEEP_RECENT_CALLS = 2
RESULT_CAP = 1200          # resultado de ferramenta guardado no histórico (a página mostra até 3000)
MAX_NUDGES = 2
AUTO = "[auto] "           # mensagens internas do sistema: não aparecem na conversa da página

SYSTEM = """You are openTARS Self-Programming: an AI agent that LIVES INSIDE a small board ({machine}) running MicroPython. The user talks to you from a web page served by this board.

YOU run the code. The user cannot: they only read your replies. Never put a program in a reply for the user to copy, save or run, and never say "save this and run it". Do the work with your tools: run_code to test or do something once, start_program for anything that keeps running. A reply that contains code but no tool call is a mistake. Write code, run it, read the output or the error, fix it, run it again. Never say "I can't" before trying code.

Rules:
- Programs must call delay(ms) inside every loop (predefined; it is how they can be stopped) and print() to report. Predefined: delay, should_stop, print, args.
- start_program replaces a program with the same name. "stop" means stop_program('all'); if nothing was running, say so.
- To change something that is running, stop it or start the new version under the same name.
- Be economical: each tool round costs tokens and providers limit them per minute. Do the whole job in ONE program, test only when unsure, and do not read /lib files (the helpers are documented below).
- Reusable pieces: save as /skills/<name>.py with a one-line docstring at the top, then `import <name>`. Library now: {skills}
- remember: durable facts (wiring, preferences, time zone). Known now: {notes}
- You cannot see the board, screen or LEDs, or hear sounds: say what you ran and what it printed, never that it "looks right".
- Reply in the user's language, briefly. Pins are 3.3 V; never drive motors, relays or mains directly from a pin; avoid GPIO 19/20 (USB), 26-37 (flash/PSRAM), 43/44 (console), 0/3/45/46 (boot) for new wiring.

Available in MicroPython: machine (Pin, I2C, PWM, ADC, UART), neopixel, framebuf, network, espnow, requests, time, math, ntptime. Not available: inspect and most of CPython's standard library.
Helpers (read /lib/*.py with read_file for details):
- `import tars`: tars.led(r,g,b) onboard RGB LED; tars.oled() ready OLED (framebuf: fill, pixel, line, rect, fill_rect, ellipse, text(str,x,y) 8x8 font = 16 chars x 8 lines, show) or None; tars.button() BOOT button (value()==0 pressed); tars.send(to,text), inbox=tars.inbox(); inbox.get(timeout_ms) -> (sender,text) or None, tars.peers(); tars.localtime() / tars.now() the clock in the user's time zone (set_timezone tool; the board syncs the clock by NTP at boot, which is UTC).
- `import gfx`: g = gfx.Gfx(tars.oled()); g.wire(gfx.CUBE, ax, ay, az) 3D wireframe, g.plot, g.bar.
Board: {board}"""

CODE_NUDGE = (AUTO + "You answered with code but did not run it. The user cannot run code; only you can. Run it now with start_program "
              "(or run_code to test first), then tell the user what happened in one or two sentences. Do not paste the code again. "
              "(Only if the user asked to SEE the code, answer with it and say you did not run it.)")


def _looks_like_code_dump(text):
    t = text or ""
    if "```" not in t:
        return False
    return any(k in t for k in ("import ", "def ", "while ", "tars.", "oled.", "print(", "for "))


def _clean_args(raw):
    """Argumentos da chamada de ferramenta: aceita texto JSON ou dict; tenta consertar o JSON cortado. Devolve (dict, erro)."""
    if isinstance(raw, dict):
        return raw, ""
    raw = (raw or "").strip()
    if not raw:
        return {}, ""
    try:
        v = json.loads(raw)
        return (v if isinstance(v, dict) else {}), ""
    except ValueError:
        pass
    for tail in ('"}', '}', '"}}', '"]}'):
        try:
            v = json.loads(raw + tail)
            return (v if isinstance(v, dict) else {}), ""
        except ValueError:
            continue
    return None, "the tool arguments were not valid JSON; send the call again with valid JSON arguments"


STOP_WORDS_PT = ("pare", "para", "parar", "pare tudo", "para tudo", "parar tudo", "pare isso", "para isso", "pare o programa", "cancela", "cancelar", "chega")
STOP_WORDS_EN = ("stop", "stop all", "stop everything", "stop all the code", "stop it", "stop that", "stop the program", "halt", "cancel", "kill all")


def _stop_command(text):
    """'pare', 'stop all'...: tratado direto, sem gastar uma chamada ao modelo (e sem risco de o modelo se confundir). Devolve 'pt', 'en' ou ''."""
    t = (text or "").lower().strip(" .!?,;:")
    if t in STOP_WORDS_PT:
        return "pt"
    if t in STOP_WORDS_EN:
        return "en"
    return ""


def _tool_name(name):
    name = (name or "").strip()
    for sep in (".", ":", "/"):
        if sep in name:
            name = name.rsplit(sep, 1)[-1]   # "functions.run_code", "default_api:run_code"
    return name


class Agent:
    def __init__(self):
        self.busy = False
        self.cancel = False
        self.history = self._load()

    def _load(self):
        txt = compat.read_text(HISTORY)
        try:
            h = json.loads(txt) if txt else []
        except ValueError:
            h = []
        # uma queda no meio de um pedido pode ter deixado uma chamada de ferramenta sem resposta: corta até o último pedido do usuário
        while h and h[-1].get("role") == "assistant" and h[-1].get("tool_calls"):
            h.pop()
        while h and h[-1].get("role") == "tool":
            h.pop()
        return h

    def _save(self):
        try:
            compat.write_text(HISTORY, json.dumps(self.history))
        except Exception:
            pass

    def clear(self):
        self.history = []
        self._save()

    def _shrink(self):
        """Encurta resultados de ferramenta antigos e corta do começo, sempre num pedido do usuário (não separa chamada de resposta)."""
        tool_idx = [i for i, m in enumerate(self.history) if m.get("role") == "tool"]
        for i in tool_idx[:-KEEP_RECENT_TOOLS]:
            c = self.history[i].get("content") or ""
            if len(c) > OLD_TOOL_RESULT:
                self.history[i]["content"] = c[:OLD_TOOL_RESULT] + "...[cut]"
        call_idx = [i for i, m in enumerate(self.history) if m.get("role") == "assistant" and m.get("tool_calls")]
        for i in call_idx[:-KEEP_RECENT_CALLS]:
            for tc in self.history[i]["tool_calls"]:
                args, _bad = _clean_args(tc.get("function", {}).get("arguments"))
                if args and any(isinstance(v, str) and len(v) > OLD_CODE for v in args.values()):
                    short = {k: (v[:OLD_CODE] + "...[cut]" if isinstance(v, str) and len(v) > OLD_CODE else v) for k, v in args.items()}
                    tc["function"]["arguments"] = json.dumps(short)   # continua sendo JSON válido: alguns provedores conferem
        while len(json.dumps(self.history)) > MAX_HISTORY_CHARS:
            idx = [i for i, m in enumerate(self.history) if m["role"] == "user" and not (m.get("content") or "").startswith(AUTO)]
            if len(idx) < 2:
                self.history = self.history[-1:]
                break
            self.history = self.history[idx[1]:]

    def system_prompt(self):
        cfg = config.get()
        info = tools.board_info()
        skills = ", ".join("%s (%s)" % (n, d) if d else n for n, d in tools.skills_index()) or "(empty: start building it)"
        board = {"oled": cfg.get("oled"), "rgb_led_pin": cfg.get("rgb_led_pin"), "boot_button_pin": 0,
                 "name": info["name"], "ip": info["ip"], "espnow_peers": info["peers"],
                 "utc_offset_hours": cfg.get("tz_offset_min", 0) / 60}
        return SYSTEM.format(machine=info["machine"] or "ESP32-S3", skills=skills, board=json.dumps(board),
                             notes=(tools.notes().strip() or "(none yet)"))

    async def run(self, text):
        if self.busy:
            raise ValueError("busy")
        self.busy, self.cancel = True, False
        cfg = config.get()
        self.history.append({"role": "user", "content": text})
        events.emit("user", text=text)
        lang = _stop_command(text)
        if lang:
            try:
                res = tools.programs.stop("all")
                n = len(res["stopped"])
                if res["stuck"]:
                    reply = ("Pedi para parar, mas %s não responde (o código não chama delay()). Reinicie a placa em Ajustes." if lang == "pt"
                             else "I asked %s to stop but it does not respond (its code never calls delay()). Restart the board in Settings.") % ", ".join(res["stuck"])
                elif lang == "pt":
                    reply = "Parei %d programa(s)." % n if n else "Não havia nenhum programa rodando."
                else:
                    reply = "Stopped %d program(s)." % n if n else "No program was running."
                events.emit("tool_call", name="stop_program", args={"name": "all"})
                events.emit("tool_result", name="stop_program", text=("stopped: " + ", ".join(res["stopped"])) if res["stopped"] else "nothing was running")
                events.emit("assistant", text=reply)
                self.history.append({"role": "assistant", "content": reply})
                events.emit("state", state="done")
            finally:
                self.busy = False
                self._save()
            return
        events.emit("state", state="thinking")
        nudges, ran_code = 0, False
        try:
            for _ in range(int(cfg.get("agent_max_rounds", 12))):
                if self.cancel:
                    events.emit("assistant", text="(stopped)")
                    break
                self._shrink()
                msgs = [{"role": "system", "content": self.system_prompt()}] + self.history
                msg = await llm.chat(cfg, msgs, tools.TOOLS)
                # guarda só o que importa (alguns provedores devolvem campos extras, como "reasoning", que só pesam)
                keep = {"role": "assistant", "content": msg.get("content")}
                if msg.get("tool_calls"):
                    keep["tool_calls"] = msg["tool_calls"]
                self.history.append(keep)
                calls = msg.get("tool_calls") or []
                if not calls:
                    # o modelo despejou o programa na resposta em vez de rodá-lo: cutuca, sem mostrar o despejo ao usuário
                    if nudges < MAX_NUDGES and not ran_code and _looks_like_code_dump(msg.get("content")):
                        nudges += 1
                        self.history.append({"role": "user", "content": CODE_NUDGE})
                        events.emit("log", text="the model answered with code instead of running it: asking it to run it")
                        continue
                    if msg.get("content"):
                        events.emit("assistant", text=msg["content"])
                    break
                if msg.get("content"):
                    events.emit("assistant", text=msg["content"])
                events.emit("state", state="working")
                for tc in calls:
                    fn = tc.get("function", {})
                    name = _tool_name(fn.get("name"))
                    if name in ("run_code", "start_program"):
                        ran_code = True
                    args, bad = _clean_args(fn.get("arguments"))
                    events.emit("tool_call", name=name, args=args or {})
                    if bad:
                        result = "error: " + bad
                    elif name not in tools.NAMES:
                        result = "error: no tool called '%s'. Tools: %s" % (name, ", ".join(sorted(tools.NAMES)))
                    else:
                        try:
                            result = await tools.call(name, args)
                        except Exception as e:
                            result = "error: " + str(e)
                    events.emit("tool_result", name=name, text=str(result)[:3000])
                    self.history.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": str(result)[:RESULT_CAP]})
                events.emit("state", state="thinking")
            else:
                events.emit("assistant", text="(stopped after %d rounds without a final answer)" % cfg.get("agent_max_rounds", 12))
            events.emit("state", state="done")
        except Exception as e:
            events.emit("error", text=str(e))
            events.emit("state", state="error")
            # um pedido que falhou sem resposta deixaria uma chamada de ferramenta órfã: tira até o último pedido do usuário
            while self.history and not (self.history[-1]["role"] == "user" and not (self.history[-1].get("content") or "").startswith(AUTO)):
                self.history.pop()
        finally:
            self.busy = False
            self._save()


agent = Agent()
