# Cliente HTTP/1.1 assíncrono (http e https) para falar com o modelo sem travar o servidor web da placa.
import asyncio
from . import compat


class HTTPError(Exception):
    pass


def _ssl_context():
    import ssl
    if compat.MICRO:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # shortcut: a placa não tem lista de autoridades certificadoras, então não confere o certificado;
        # trocar por ctx.load_verify_locations(...) quando houver um pacote de CAs no sistema de arquivos.
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return True  # CPython: contexto padrão, que confere o certificado


def split_url(url):
    proto, _, rest = url.partition("://")
    hostport, slash, path = rest.partition("/")
    host, _, port = hostport.partition(":")
    https = proto == "https"
    return https, host, int(port) if port else (443 if https else 80), "/" + path, hostport


async def _do(method, url, headers, body):
    https, host, port, path, hostport = split_url(url)
    if https:
        try:
            reader, writer = await asyncio.open_connection(host, port, ssl=_ssl_context(), server_hostname=host)
        except TypeError:  # versões do asyncio sem server_hostname: o SNI sai do host
            reader, writer = await asyncio.open_connection(host, port, ssl=_ssl_context())
    else:
        reader, writer = await asyncio.open_connection(host, port)
    try:
        if isinstance(body, str):
            body = body.encode()
        lines = ["{} {} HTTP/1.1".format(method, path), "Host: " + hostport, "Connection: close",
                 "User-Agent: openTARS-SP/0.1", "Accept-Encoding: identity"]
        for k, v in (headers or {}).items():
            lines.append(k + ": " + v)
        if body is not None:
            lines.append("Content-Length: %d" % len(body))
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
        if body:
            writer.write(body)
        await writer.drain()
        status_line = await reader.readline()
        if not status_line:
            raise HTTPError("connection closed without a reply")
        status = int(status_line.split(b" ")[1])
        resp_headers = {}
        while True:
            h = await reader.readline()
            if h in (b"\r\n", b"\n", b""):
                break
            k, _, v = h.decode().partition(":")
            resp_headers[k.strip().lower()] = v.strip()
        data = bytearray()
        if "chunked" in resp_headers.get("transfer-encoding", ""):
            while True:
                size = int((await reader.readline()).split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    break
                data.extend(await reader.readexactly(size))
                await reader.readline()
        elif "content-length" in resp_headers:
            n = int(resp_headers["content-length"])
            if n:
                data.extend(await reader.readexactly(n))
        else:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                data.extend(chunk)
        return status, resp_headers, bytes(data)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def request(method, url, headers=None, body=None, timeout_s=60):
    try:
        return await asyncio.wait_for(_do(method, url, headers, body), timeout_s)
    except asyncio.TimeoutError:
        raise HTTPError("timed out after %d s" % timeout_s)
    except OSError as e:  # [Errno 113] ECONNABORTED, 111 ECONNREFUSED, 110 ETIMEDOUT, DNS...: diz com quem tentou falar
        _, host, port, _, _ = split_url(url)
        raise HTTPError("could not connect to %s:%d (%s)" % (host, port, e))
