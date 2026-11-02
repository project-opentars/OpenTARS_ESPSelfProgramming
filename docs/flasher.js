// Passo 2 do gravador: copia o openTARS para uma placa que já tem MicroPython, pelo USB (Web Serial),
// usando o REPL "raw" do MicroPython, o mesmo caminho do mpremote. Não apaga /data, /skills nem /programs.
const enc = new TextEncoder();
const dec = new TextDecoder();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const DIRS_KEPT = ["data", "skills", "programs"];

class RawRepl {
  async open(port) {
    this.port = port;
    await port.open({ baudRate: 115200 });
    this.reader = port.readable.getReader();
    this.writer = port.writable.getWriter();
    this.buf = "";
    this.done = this.pump();
  }

  async pump() {
    try {
      for (;;) {
        const { value, done } = await this.reader.read();
        if (done) break;
        this.buf += dec.decode(value, { stream: true });
      }
    } catch (e) {
      this.err = e;
    }
  }

  async until(text, ms = 8000) {
    const end = Date.now() + ms;
    for (;;) {
      const i = this.buf.indexOf(text);
      if (i >= 0) {
        const out = this.buf.slice(0, i);
        this.buf = this.buf.slice(i + text.length);
        return out;
      }
      if (this.err) throw this.err;
      if (Date.now() > end) throw new Error("the board did not answer (waiting for " + JSON.stringify(text) + ")");
      await sleep(20);
    }
  }

  async write(data) {
    const b = typeof data === "string" ? enc.encode(data) : data;
    for (let i = 0; i < b.length; i += 256) {   // pedaços pequenos, como o mpremote: a entrada do REPL é lenta
      await this.writer.write(b.slice(i, i + 256));
      await sleep(4);
    }
  }

  async enter() {
    for (let tries = 0; tries < 3; tries++) {
      await this.write("\r\x03\x03");             // Ctrl-C duas vezes: para o openTARS ou o programa que estiver rodando
      await sleep(300);
      this.buf = "";
      await this.write("\r\x01");                 // Ctrl-A: REPL raw
      try {
        await this.until("raw REPL; CTRL-B to exit\r\n>", 3000);
        return;
      } catch (e) {
        if (tries === 2) throw new Error("no MicroPython prompt on this port. Is MicroPython installed (step 1)?");
      }
    }
  }

  async exec(code, ms = 15000) {
    await this.write(code);
    await this.write("\x04");
    await this.until("OK", ms);
    const out = await this.until("\x04", ms);
    const err = await this.until("\x04", ms);
    await this.until(">", ms);
    if (err.trim()) throw new Error(err.trim().split("\n").pop());
    return out;
  }

  async close() {
    try { await this.reader.cancel(); } catch (e) {}
    try { this.reader.releaseLock(); this.writer.releaseLock(); } catch (e) {}
    try { await this.port.close(); } catch (e) {}
  }
}

function b64(bytes) {
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

async function copySystem(ui) {
  const files = await (await fetch("flasher/files.json", { cache: "no-store" })).json();
  const total = files.reduce((a, f) => a + f.size, 0);
  const port = await navigator.serial.requestPort();
  const repl = new RawRepl();
  await repl.open(port);
  let sent = 0;
  try {
    ui.log("Connecting to MicroPython…");
    await repl.enter();
    const dirs = new Set(DIRS_KEPT);
    for (const f of files) {
      const parts = f.path.split("/");
      for (let i = 1; i < parts.length; i++) dirs.add(parts.slice(0, i).join("/"));
    }
    const list = [...dirs].sort((a, b) => a.split("/").length - b.split("/").length);
    await repl.exec("import os\nfor d in " + JSON.stringify(list) + ":\n try:\n  os.mkdir('/'+d)\n except OSError:\n  pass\n");
    for (const f of files) {
      ui.log("Copying " + f.path);
      const res = await fetch("flasher/board/" + f.path, { cache: "no-store" });
      if (!res.ok) throw new Error("could not download " + f.path + " from this site");
      const data = new Uint8Array(await res.arrayBuffer());
      await repl.exec("from binascii import a2b_base64 as _d\n_f=open('/" + f.path + "','wb')\n");
      for (let i = 0; i < data.length; i += 2048) {
        const chunk = data.subarray(i, i + 2048);
        await repl.exec("_f.write(_d('" + b64(chunk) + "'))\n");
        sent += chunk.length;
        ui.progress(sent / total);
      }
      const size = (await repl.exec("_f.close()\nprint(os.stat('/" + f.path + "')[6])\n")).trim();
      if (Number(size) !== data.length) throw new Error(f.path + " arrived with " + size + " bytes instead of " + data.length);
    }
    ui.log("All " + files.length + " files copied and checked. Restarting the board…");
    await repl.write("import machine\r\nmachine.reset()\r\x04");   // a porta some no reinício: não espera resposta
    await sleep(300);
  } finally {
    await repl.close();
  }
}

const btn = document.getElementById("copy-btn");
const logEl = document.getElementById("copy-log");
const bar = document.getElementById("copy-bar");
const done = document.getElementById("copy-done");

if (!("serial" in navigator)) {
  document.querySelectorAll(".needs-serial").forEach((el) => (el.hidden = true));
  document.querySelectorAll(".no-serial").forEach((el) => (el.hidden = false));
}

btn?.addEventListener("click", async () => {
  btn.disabled = true;
  done.hidden = true;
  logEl.textContent = "";
  bar.value = 0;
  bar.hidden = false;
  const ui = {
    log: (t) => { logEl.textContent = t; },
    progress: (p) => { bar.value = p; },
  };
  try {
    await copySystem(ui);
    bar.value = 1;
    done.hidden = false;
  } catch (e) {
    if (e && e.name === "NotFoundError") ui.log("No port chosen.");
    else ui.log("Stopped: " + (e && e.message ? e.message : e) + ". Unplug and plug the board back in, then try again.");
  } finally {
    btn.disabled = false;
  }
});
