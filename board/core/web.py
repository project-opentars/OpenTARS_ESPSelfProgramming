# Servidor HTTP mínimo em asyncio: rotas da API em JSON e arquivos estáticos de /www (usa o .gz quando existe).
import asyncio
import json
from . import compat

MAX_BODY = 256 * 1024
TYPES = {"py": "text/plain; charset=utf-8", "html": "text/html; charset=utf-8", "js": "application/javascript", "css": "text/css",
         "json": "application/json", "png": "image/png", "svg": "image/svg+xml", "ico": "image/x-icon",
         "woff2": "font/woff2", "ttf": "font/ttf", "webmanifest": "application/manifest+json", "txt": "text/plain"}
STATUS = {200: "OK", 204: "No Content", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed",
          409: "Conflict", 413: "Payload Too Large", 500: "Internal Server Error"}


def unquote(s):
    s = s.replace("+", " ")
    if "%" not in s:
        return s
    out = bytearray()
    i, b = 0, s.encode()
    while i < len(b):
        if b[i] == 37 and i + 2 < len(b):  # '%'
            try:
                out.append(int(b[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.append(b[i])
        i += 1
    return out.decode()


def parse_query(qs):
    q = {}
    for part in qs.split("&"):
        if part:
            k, _, v = part.partition("=")
            q[unquote(k)] = unquote(v)
    return q


def _peer_ip(writer):
    """IP de quem fez o pedido, ou "" se a plataforma não informar."""
    try:
        peer = writer.get_extra_info("peername")
    except Exception:
        return ""
    if isinstance(peer, tuple) and peer:
        return str(peer[0])
    if isinstance(peer, (bytes, bytearray)) and len(peer) >= 8:   # sockaddr cru do lwIP: família(2) porta(2) ip(4)
        return "%d.%d.%d.%d" % (peer[4], peer[5], peer[6], peer[7])
    return ""


class Request:
    def __init__(self, method, path, query, headers, body):
        self.method, self.path, self.query, self.headers, self.body = method, path, query, headers, body
        self.client = ""

    def json(self):
        try:
            return json.loads(self.body or b"{}")
        except ValueError:
            return {}


def reply(obj, status=200):
    return status, "application/json", json.dumps(obj)


class Server:
    def __init__(self, static_dir="/www"):
        self.routes = {}
        self.static_dir = static_dir

    def route(self, method, path):
        def deco(fn):
            self.routes[(method, path)] = fn
            return fn
        return deco

    async def start(self, host="0.0.0.0", port=80):
        return await asyncio.start_server(self._handle, host, port)

    async def _handle(self, reader, writer):
        try:
            line = await asyncio.wait_for(reader.readline(), 15)
            if not line:
                return
            parts = line.decode().split(" ")
            if len(parts) < 2:
                return
            method, target = parts[0], parts[1]
            headers = {}
            while True:
                h = await asyncio.wait_for(reader.readline(), 15)
                if h in (b"\r\n", b"\n", b""):
                    break
                k, _, v = h.decode().partition(":")
                headers[k.strip().lower()] = v.strip()
            n = int(headers.get("content-length", "0") or 0)
            if n > MAX_BODY:
                await self._send(writer, 413, "application/json", '{"error":"body too large"}')
                return
            body = await reader.readexactly(n) if n else b""
            path, _, qs = target.partition("?")
            req = Request(method, unquote(path), parse_query(qs), headers, body)
            req.client = _peer_ip(writer)
            handler = self.routes.get((method, req.path))
            if handler:
                try:
                    status, ctype, payload = await handler(req)
                except Exception as e:
                    status, ctype, payload = reply({"error": str(e), "trace": compat.format_exc(e)[-800:]}, 500)
                await self._send(writer, status, ctype, payload)
            elif method == "GET" and not req.path.startswith("/api/"):
                await self._static(writer, req.path)
            else:
                await self._send(writer, 404, "application/json", '{"error":"not found"}')
        except Exception:
            pass  # cliente fechou no meio: não derruba o servidor
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _send(self, writer, status, ctype, payload, extra=""):
        if isinstance(payload, str):
            payload = payload.encode()
        head = "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n{}\r\n".format(
            status, STATUS.get(status, "OK"), ctype, len(payload), extra)
        writer.write(head.encode())
        if payload:
            writer.write(payload)
        await writer.drain()

    async def _static(self, writer, path):
        if path == "/" or path == "":
            path = "/index.html"
        if ".." in path:
            await self._send(writer, 404, "text/plain", "not found")
            return
        full = self.static_dir + path
        gz = compat.exists(full + ".gz")
        if not gz and not compat.exists(full):
            await self._send(writer, 404, "text/plain", "not found")
            return
        ext = path.rsplit(".", 1)[-1]
        fname = compat.fs(full + (".gz" if gz else ""))
        import os
        size = os.stat(fname)[6]
        cache = "no-cache" if ext == "html" else "max-age=86400"
        head = "HTTP/1.1 200 OK\r\nContent-Type: {}\r\nContent-Length: {}\r\nCache-Control: {}\r\nConnection: close\r\n{}\r\n".format(
            TYPES.get(ext, "application/octet-stream"), size, cache, "Content-Encoding: gzip\r\n" if gz else "")
        writer.write(head.encode())
        buf = bytearray(2048)
        with open(fname, "rb") as f:
            while True:
                k = f.readinto(buf)
                if not k:
                    break
                writer.write(buf[:k] if k < len(buf) else buf)
                await writer.drain()
