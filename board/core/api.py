# Rotas HTTP da página.
import asyncio
import json
import os
from . import agent as agent_mod, compat, config, events, net, programs, tools
from .web import Server, reply

VERSION = "0.2.0"
SYSTEM_PATHS = ("/core", "/lib", "/www", "/main.py", "/boot.py")


def _is_system(path):
    return any(path == p or path.startswith(p + "/") for p in SYSTEM_PATHS)
BOOT_CAUSE = ""


def make_server():
    srv = Server("/www")
    ag = agent_mod.agent

    @srv.route("GET", "/api/status")
    async def status(req):
        cfg = config.get()
        st = net.status()
        return reply({"version": VERSION, "uptime_s": compat.ticks_ms() // 1000, "boot_cause": BOOT_CAUSE,
                      "network": st, "memory": compat.mem_info(), "busy": ag.busy,
                      "programs": programs.all_info(), "peers": net.peers_info(), "last_event": events.last_id(),
                      "bridge": {"connected": ag.connected(), "available": ag.available, "harness": cfg.get("harness"), "working": ag.working},
                      "lang": cfg.get("lang"), "client_ip": req.client})

    @srv.route("GET", "/api/events")
    async def get_events(req):
        try:
            since = int(req.query.get("since", "0") or 0)
        except ValueError:
            since = 0
        end = compat.ticks_ms() + 12000
        while True:  # espera até 12 s por novidade: a página fica atualizada sem martelar a placa
            evs = events.since(since)
            if evs or compat.ticks_diff(end, compat.ticks_ms()) <= 0 or req.query.get("wait") != "1":
                return reply({"events": evs, "last": events.last_id(), "busy": ag.busy})
            await asyncio.sleep(0.15)

    @srv.route("POST", "/api/chat")
    async def chat(req):
        text = (req.json().get("text") or "").strip()
        if not text:
            return reply({"error": "empty"}, 400)
        if ag.busy:
            return reply({"error": "busy"}, 409)
        asyncio.create_task(ag.run(text))
        return reply({"ok": True})

    @srv.route("POST", "/api/chat/stop")
    async def chat_stop(req):
        ag.cancel = True
        return reply({"ok": True})

    @srv.route("POST", "/api/chat/clear")
    async def chat_clear(req):
        if ag.busy:
            return reply({"error": "busy"}, 409)
        ag.clear()
        return reply({"ok": True})

    @srv.route("GET", "/api/chat/history")
    async def chat_history(req):
        return reply({"items": ag.history, "last": events.last_id(), "busy": ag.busy})

    @srv.route("POST", "/api/bridge/poll")
    async def bridge_poll(req):
        return reply({"job": await ag.poll(req.json().get("available") or [])})

    @srv.route("POST", "/api/bridge/event")
    async def bridge_event(req):
        d = req.json()
        return reply({"cancel": ag.bridge_event(d.get("id"), d.get("kind"), str(d.get("text") or ""))})

    @srv.route("POST", "/api/bridge/done")
    async def bridge_done(req):
        d = req.json()
        ag.bridge_done(d.get("id"), d.get("ok"), d.get("text"))
        return reply({"ok": True})

    @srv.route("POST", "/api/tool")
    async def tool(req):
        """Como o programa de IA age na placa: {"name": "run_code", "args": {...}} -> texto curto."""
        d = req.json()
        name, args = d.get("name"), d.get("args") if isinstance(d.get("args"), dict) else {}
        if name not in tools.NAMES:
            return reply({"error": "no tool called %r. Tools: %s" % (name, ", ".join(sorted(tools.NAMES)))}, 400)
        events.emit("tool_call", name=name, args=args)
        try:
            result = str(await tools.call(name, args))
        except Exception as e:
            result = "error: " + str(e)
        events.emit("tool_result", name=name, text=result[:3000])
        ag.note_tool(name, args, result)
        return reply({"result": result})

    @srv.route("GET", "/api/config")
    async def get_config(req):
        return reply({"config": config.public()})

    @srv.route("POST", "/api/config")
    async def set_config(req):
        data = req.json()
        if str(data.get("wifi_password", "")).startswith("********"):
            del data["wifi_password"]  # a página manda de volta o valor mascarado: não sobrescreve
        config.save(data)
        return reply({"config": config.public(), "rejected": config.last_rejected})

    @srv.route("POST", "/api/wifi/connect")
    async def wifi_connect(req):
        d = req.json()
        ssid = (d.get("ssid") or "").strip()
        if not ssid:
            return reply({"ok": False, "error": "no_ssid"}, 400)
        return reply(await net.connect_wifi(ssid, d.get("password") or ""))

    @srv.route("GET", "/api/wifi/scan")
    async def wifi_scan(req):
        return reply({"networks": net.scan_wifi()})

    @srv.route("GET", "/api/files")
    async def list_files(req):
        path = req.query.get("path", "/") or "/"
        items = []
        try:
            for n in sorted(os.listdir(compat.fs(path))):
                full = path.rstrip("/") + "/" + n
                d = compat.is_dir(full)
                items.append({"name": n, "path": full, "dir": d, "size": 0 if d else os.stat(compat.fs(full))[6]})
        except OSError:
            return reply({"error": "no such folder"}, 404)
        return reply({"path": path, "items": items})

    @srv.route("GET", "/api/file")
    async def read_file(req):
        txt = compat.read_text(req.query.get("path", ""))
        if txt is None:
            return reply({"error": "not found"}, 404)
        return 200, "text/plain; charset=utf-8", txt

    @srv.route("POST", "/api/file")
    async def write_file(req):
        path = req.query.get("path", "")
        if not path.startswith("/") or ".." in path:
            return reply({"error": "bad path"}, 400)
        if _is_system(path) and req.query.get("force") != "1":
            return reply({"error": "system file: turn on developer mode in Settings to change it"}, 403)
        try:
            text = req.body.decode("utf-8")
        except UnicodeError:
            return reply({"error": "only text files can be saved here"}, 400)
        compat.write_text(path, text)
        return reply({"ok": True, "path": path})

    @srv.route("POST", "/api/file/delete")
    async def delete_file(req):
        d = req.json()
        path = d.get("path", "")
        if _is_system(path) and not d.get("force"):
            return reply({"error": "system file: turn on developer mode in Settings to delete it"}, 403)
        try:
            os.remove(compat.fs(path))
        except OSError:
            return reply({"error": "not found"}, 404)
        return reply({"ok": True})

    @srv.route("GET", "/api/programs")
    async def list_programs(req):
        return reply({"programs": programs.all_info(), "autostart": config.get().get("autostart", [])})

    @srv.route("POST", "/api/run")
    async def run(req):
        d = req.json()
        try:
            p = programs.start(name=d.get("name") or None, code=d.get("code"), path=d.get("path"))
        except ValueError as e:
            return reply({"error": str(e)}, 400)
        return reply({"program": p.info()})

    @srv.route("POST", "/api/stop")
    async def stop(req):
        return reply(programs.stop(req.json().get("name") or "all"))

    @srv.route("GET", "/api/program/log")
    async def program_log(req):
        p = programs.get(req.query.get("name", ""))
        if not p:
            return reply({"error": "not found"}, 404)
        return reply({"program": p.info(), "log": p.log[-200:]})

    @srv.route("POST", "/api/autostart")
    async def autostart(req):
        return reply({"result": await tools.call("set_autostart", req.json())})

    @srv.route("GET", "/api/peers")
    async def peers(req):
        return reply({"peers": net.peers_info(), "me": net.status()})

    @srv.route("POST", "/api/espnow/send")
    async def espnow_send(req):
        d = req.json()
        return reply({"result": await net.send_text(d.get("to", ""), d.get("text", ""))})

    @srv.route("POST", "/api/espnow/run")
    async def espnow_run(req):
        d = req.json()
        try:
            timeout = max(2, min(int(d.get("timeout_s") or 15), 120))
        except (TypeError, ValueError):
            timeout = 15
        return reply({"result": await net.remote_run(d.get("to", ""), d.get("code", ""), timeout)})

    @srv.route("POST", "/api/reboot")
    async def reboot(req):
        async def later():
            await asyncio.sleep(0.6)
            import machine
            try:
                compat.write_text("/data/state.json", json.dumps({"clean": True}))  # reinício pedido por quem usa: não é queda
            except Exception:
                pass
            machine.reset()
        asyncio.create_task(later())
        return reply({"ok": True})

    return srv
