# Ferramentas que o modelo pode chamar. Cada uma recebe um dict de argumentos e devolve texto curto.
import json
import os
from . import compat, config, programs

WRITABLE = ("/skills/", "/programs/", "/data/files/")
NOTES = "/data/notes.md"
MAX_FILE = 64 * 1024
MAX_NOTES = 4000


def _schema(name, desc, props=None, required=()):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": list(required)}}}


S, I, B = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}

TOOLS = [
    _schema("run_code", "Run MicroPython code on this board; returns what it printed or the error with its line. Use it to test and for one-off actions. "
            "If still running after timeout_s it continues as a background program.", {"code": S, "timeout_s": I}, ["code"]),
    _schema("start_program", "Run code in the background (animations, monitors, loops, buttons, messages). Replaces a running program of the same name. "
            "Give code (saved as /programs/<name>.py) or path.", {"name": S, "code": S, "path": S}, ["name"]),
    _schema("stop_program", "Stop a background program by name, or 'all'.", {"name": S}),
    _schema("list_programs", "Programs with status and errors."),
    _schema("program_log", "Last printed lines of a program, and its error.", {"name": S, "lines": I}, ["name"]),
    _schema("write_file", "Create or overwrite a text file in /skills (reusable modules), /programs or /data/files.", {"path": S, "content": S}, ["path", "content"]),
    _schema("read_file", "Read a text file (any folder, e.g. /lib).", {"path": S}, ["path"]),
    _schema("list_files", "List a folder.", {"path": S}),
    _schema("delete_file", "Delete a file in /skills, /programs or /data/files.", {"path": S}, ["path"]),
    _schema("remember", "Save a short durable fact (wiring, preferences). You see all notes every time.", {"note": S}, ["note"]),
    _schema("set_autostart", "Start a program file at power-on (enabled true) or stop doing so.", {"path": S, "enabled": B}, ["path", "enabled"]),
    _schema("set_timezone", "Set the user's UTC offset in hours (São Paulo -3, New York -5, Berlin 1) for tars.localtime().", {"hours": {"type": "number"}}, ["hours"]),
    _schema("board_info", "Memory, Wi-Fi, IP, programs, pins, files in /skills."),
    _schema("espnow_peers", "Other openTARS boards seen over ESP-NOW."),
    _schema("espnow_send", "Send a text message to another board (name or MAC) or 'all'.", {"to": S, "text": S}, ["to", "text"]),
    _schema("espnow_run", "Run MicroPython code on ANOTHER board over ESP-NOW; returns its output.", {"to": S, "code": S, "timeout_s": I}, ["to", "code"]),
]


NAMES = set(t["function"]["name"] for t in TOOLS)


def _writable(path):
    if path == NOTES:
        return True  # a memória pode ser reescrita mais curta
    return path.startswith("/") and ".." not in path and any(path.startswith(w) for w in WRITABLE)


def _clip(text, n=3000):
    text = str(text)
    return text if len(text) <= n else text[:n] + "\n...[%d more characters cut]" % (len(text) - n)


def api_summary(txt):
    """Docstring de um módulo e as linhas de def/class: o suficiente para saber a API sem pagar o arquivo todo em tokens."""
    lines = txt.split("\n")
    out, inside = [], False
    for ln in lines:
        s = ln.strip()
        if not out and not inside and s.startswith('"""'):
            inside = True
        if inside:
            out.append(ln)
            if s.endswith('"""') and len(out) > 1 or (s.count('"""') == 2):
                inside = False
            continue
        if ln.startswith(("def ", "class ")) or ln.startswith("    def ") or (ln[:1].isupper() and " = " in ln.split("(")[0]):
            out.append(ln.split(":")[0] + ":" if ln.rstrip().endswith(":") else ln[:100])
    return _clip("\n".join(out) + "\n(summary of the API; the system prompt documents how to use it)", 1500)


def notes():
    return compat.read_text(NOTES, "") or ""


def skills_index():
    """Uma linha por módulo em /skills: o nome e a primeira linha da docstring."""
    out = []
    try:
        names = sorted(os.listdir(compat.fs("/skills")))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".py"):
            continue
        first = ""
        txt = compat.read_text("/skills/" + n, "") or ""
        s = txt.lstrip()
        if s.startswith('"""') or s.startswith("'''"):
            first = s[3:].split("\n", 1)[0].strip().strip('"\'')
        elif s.startswith("#"):
            first = s[1:].split("\n", 1)[0].strip()
        out.append((n[:-3], first))
    return out


def _program_report(p):
    log = p.log[-60:]
    head = "program '%s' status=%s runtime=%d ms" % (p.name, p.status, compat.ticks_diff(p.ended or compat.ticks_ms(), p.started))
    body = "\n".join(log) if log else "(printed nothing)"
    return _clip(head + "\n" + body, 3500)


async def call(name, args):
    from . import net
    cfg = config.get()
    if name == "run_code":
        timeout = max(1, min(int(args.get("timeout_s") or 10), 120))
        p = programs.start(code=args.get("code", ""))
        done = await programs.await_done(p, timeout * 1000)
        rep = _program_report(p)
        if not done:
            rep += "\n(still running in the background as '%s': use program_log or stop_program)" % p.name
        return rep
    if name == "start_program":
        pname = (args.get("name") or "").strip().replace("/", "_").replace(" ", "_")
        if not pname:
            return "error: give a name"
        path = args.get("path")
        if args.get("code"):
            path = "/programs/%s.py" % pname
            compat.write_text(path, args["code"])
        if not path:
            return "error: give code or path"
        old = programs.get(pname)
        replaced = bool(old and old.status in ("starting", "running"))
        if replaced:
            programs.stop(pname)   # mesmo nome = nova versão: para a velha e começa a nova
        p = programs.start(name=pname, path=path)
        done = await programs.await_done(p, 1500)  # pega erros de sintaxe e falhas logo no começo
        return ("(replaced the running '%s')\n" % pname if replaced else "") + _program_report(p) + ("" if done else "\n(running in the background)")
    if name == "stop_program":
        res = programs.stop(args.get("name") or "all")
        msg = "stopped: %s" % (", ".join(res["stopped"]) or "nothing")
        if res["stuck"]:
            msg += ("\nDID NOT STOP: %s. The code never calls delay(), so it cannot be interrupted; the only way out is restarting "
                    "the board (tell the user, and fix the code to call delay() inside loops)." % ", ".join(res["stuck"]))
        return msg
    if name == "list_programs":
        return json.dumps(programs.all_info()) if programs.all_info() else "no programs"
    if name == "program_log":
        p = programs.get(args.get("name", ""))
        if not p:
            return "no program named " + args.get("name", "")
        n = max(1, min(int(args.get("lines") or 40), 200))
        return _clip("status=%s\n%s%s" % (p.status, "\n".join(p.log[-n:]), ("\nERROR:\n" + p.error) if p.error else ""))
    if name == "write_file":
        path, content = args.get("path", ""), args.get("content", "")
        if not _writable(path):
            return "error: you can only write under " + ", ".join(WRITABLE) + " (system files are protected)"
        if len(content) > MAX_FILE:
            return "error: file too big (max %d bytes)" % MAX_FILE
        compat.write_text(path, content)
        return "saved %s (%d bytes)" % (path, len(content))
    if name == "read_file":
        path = args.get("path", "")
        txt = compat.read_text(path if path.startswith("/") else "/" + path)
        if txt is None:
            return "error: not found"
        if (path if path.startswith("/") else "/" + path).startswith("/lib/"):
            return api_summary(txt)   # os helpers já estão descritos no prompt: devolver o arquivo inteiro só gasta tokens
        return _clip(txt, 6000)
    if name == "list_files":
        path = args.get("path") or "/"
        try:
            items = []
            for n in sorted(os.listdir(compat.fs(path))):
                full = path.rstrip("/") + "/" + n
                items.append(n + ("/" if compat.is_dir(full) else " (%d bytes)" % os.stat(compat.fs(full))[6]))
            return "\n".join(items) or "(empty)"
        except OSError:
            return "error: no such folder"
    if name == "delete_file":
        path = args.get("path", "")
        if not _writable(path):
            return "error: only files under " + ", ".join(WRITABLE) + " can be deleted"
        try:
            os.remove(compat.fs(path))
            return "deleted " + path
        except OSError:
            return "error: not found"
    if name == "remember":
        note = (args.get("note") or "").strip().replace("\n", " ")
        cur = notes()
        if len(cur) + len(note) > MAX_NOTES:
            return ("error: notes are full (%d characters). Read /data/notes.md and rewrite it shorter with write_file "
                    "(path /data/notes.md), then remember again." % len(cur))
        compat.write_text(NOTES, cur + "- " + note + "\n")
        return "remembered"
    if name == "set_autostart":
        path, on = args.get("path", ""), bool(args.get("enabled"))
        auto = [a for a in cfg.get("autostart", []) if a.get("path") != path]
        if on:
            if not compat.exists(path):
                return "error: file not found: " + path
            auto.append({"name": path.rsplit("/", 1)[-1].replace(".py", ""), "path": path})
        config.save({"autostart": auto})
        return "autostart now: " + (", ".join(a["path"] for a in auto) or "nothing")
    if name == "set_timezone":
        try:
            hours = float(args.get("hours"))
        except (TypeError, ValueError):
            return "error: hours must be a number, for example -3"
        if not -12 <= hours <= 14:
            return "error: hours must be between -12 and 14"
        config.save({"tz_offset_min": int(round(hours * 60))})
        return "time zone set to UTC%+g" % hours
    if name == "board_info":
        return json.dumps(board_info())
    if name == "espnow_peers":
        return json.dumps(net.peers_info()) if net.peers_info() else "no other boards seen yet"
    if name == "espnow_send":
        return await net.send_text(args.get("to", ""), args.get("text", ""))
    if name == "espnow_run":
        timeout = max(2, min(int(args.get("timeout_s") or 15), 120))
        return _clip(await net.remote_run(args.get("to", ""), args.get("code", ""), timeout))
    return "error: unknown tool " + name


def board_info():
    from . import net
    import sys
    cfg = config.get()
    st = net.status()
    return {"memory_free_kb": compat.mem_info()["free"] // 1024, "mode": st.get("mode"), "ssid": st.get("ssid"), "ip": st.get("ip"),
            "name": st.get("name"), "channel": st.get("channel"), "peers": len(net.peers_info()),
            "running": [p["name"] for p in programs.all_info() if p["status"] == "running"],
            "skills": [n for n, _ in skills_index()], "oled": cfg.get("oled"), "rgb_led_pin": cfg.get("rgb_led_pin"),
            "utc_offset_min": cfg.get("tz_offset_min", 0), "autostart": [a.get("path") for a in cfg.get("autostart", [])],
            "machine": getattr(os.uname(), "machine", sys.platform) if hasattr(os, "uname") else sys.platform}
