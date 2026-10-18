# Rotas HTTP da página.
import asyncio
import json
import os
from . import agent as agent_mod, compat, config, events, llm, net, programs, tools
from .web import Server, reply

VERSION = "0.1.0"
BOOT_CAUSE = ""


def make_server():
    srv = Server("/www")
    ag = agent_mod.agent

    @srv.route("GET", "/api/status")
    async def status(req):
        return reply({"version": VERSION, "uptime_s": compat.ticks_ms() // 1000, "boot_cause": BOOT_CAUSE,
                      "network": net.status(), "memory": compat.mem_info(), "busy": ag.busy,
                      "programs": programs.all_info(), "peers": net.peers_info(), "last_event": events.last_id()})

    @srv.route("GET", "/api/events")
    async def get_events(req):
        since = int(req.query.get("since", "0") or 0)
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
        out = []
        for m in ag.history:
            if m["role"] == "user":
                out.append({"kind": "user", "text": m.get("content", "")})
            elif m["role"] == "assistant":
                if m.get("content"):
                    out.append({"kind": "assistant", "text": m["content"]})
                for tc in m.get("tool_calls") or []:
                    try:
                        args = json.loads(tc["function"].get("arguments") or "{}")
                    except ValueError:
                        args = {}
                    out.append({"kind": "tool_call", "name": tc["function"]["name"], "args": args})
            elif m["role"] == "tool":
                out.append({"kind": "tool_result", "text": str(m.get("content", ""))[:3000]})
        return reply({"items": out, "last": events.last_id(), "busy": ag.busy})

    @srv.route("GET", "/api/config")
    async def get_config(req):
        return reply({"config": config.public(), "presets": llm.PRESETS})

    @srv.route("POST", "/api/config")
    async def set_config(req):
        data = req.json()
        for secret in ("llm_api_key", "wifi_password"):
            if secret in data and str(data[secret]).startswith("********"):
                del data[secret]  # a página manda de volta o valor mascarado: não sobrescreve
        config.save(data)
        return reply({"config": config.public()})

    @srv.route("GET", "/api/models")
    async def models(req):
        try:
            return reply({"models": await llm.list_models(config.get())})
        except Exception as e:
            return reply({"error": str(e)}, 400)

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
        compat.write_text(path, req.body.decode("utf-8"))
        return reply({"ok": True, "path": path})

    @srv.route("POST", "/api/file/delete")
    async def delete_file(req):
        path = req.json().get("path", "")
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
        return reply({"result": await net.remote_run(d.get("to", ""), d.get("code", ""), int(d.get("timeout_s") or 15))})

    @srv.route("POST", "/api/reboot")
    async def reboot(req):
        async def later():
            await asyncio.sleep(0.6)
            import machine
            machine.reset()
        asyncio.create_task(later())
        return reply({"ok": True})

    return srv
