#!/usr/bin/env python3
"""openTARS bridge: lets the AI program already installed on this computer (claude, codex, opencode, pi, grok) drive the board.
Run:   python3 bridge.py http://<board address>      (the address is remembered for next time)
Only Python 3 is needed. Nothing is installed and nothing leaves this computer except the board's own HTTP calls."""
import json, os, re, shutil, signal, subprocess, sys, tempfile, threading, time, urllib.request

SAVED = os.path.join(os.path.expanduser("~"), ".opentars-board")

# name -> how to run it once, without a screen. {m} adds the model flag when the user chose one.
HARNESSES = {
    "claude": (["claude", "-p", "{prompt}", "--allowedTools", "Bash", "--no-session-persistence"], ["--model", "{m}"]),
    "codex": (["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "workspace-write",
               "-c", "sandbox_workspace_write.network_access=true", "{prompt}"], ["-m", "{m}"]),
    "opencode": (["opencode", "run", "--auto", "{prompt}"], ["-m", "{m}"]),
    "pi": (["pi", "-p", "{prompt}", "--no-session"], ["--model", "{m}"]),
    "grok": (["grok", "-p", "{prompt}", "--always-approve"], ["-m", "{m}"]),
}

HOWTO = """How to act on the board: run this in a shell (it prints the result):
  python3 {me} tool {board} NAME [key=value ...]
Code or file content goes on standard input:
  python3 {me} tool {board} run_code timeout_s=10 <<'PY'
  <MicroPython code>
  PY
  python3 {me} tool {board} start_program name=blink <<'PY'
  ...
  PY
  python3 {me} tool {board} write_file path=/skills/x.py <<'PY'
  ...
  PY
Other tools only take key=value: python3 {me} tool {board} stop_program name=all
"""


def post(url, data, timeout=35):
    req = urllib.request.Request(url, json.dumps(data).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def tool(board, name, pairs):
    args = {}
    for p in pairs:
        k, _, v = p.partition("=")
        args[k] = int(v) if re.fullmatch(r"-?\d+", v) else float(v) if re.fullmatch(r"-?\d+\.\d+", v) else {"true": True, "false": False}.get(v, v)
    if not sys.stdin.isatty():
        text = sys.stdin.read()
        if text.strip():
            args["content" if name == "write_file" else "code"] = text
    print(post(board + "/api/tool", {"name": name, "args": args}, 140).get("result") or "(no result)")


def run_job(board, job, found):
    name = job.get("harness") if job.get("harness") in found else found[0]
    base, model = HARNESSES[name]
    prompt = "\n\n".join([job["guide"], HOWTO.format(me=os.path.abspath(__file__), board=board),
                          "Conversation so far:\n" + "\n".join("%s: %s" % (m["role"], m["text"]) for m in job.get("recent") or []) if job.get("recent") else "",
                          "user: " + job["text"]])
    argv = [prompt if a == "{prompt}" else a for a in base]
    if job.get("model"):
        argv += [job["model"] if a == "{m}" else a for a in model]
    tmp = tempfile.mkdtemp(prefix="opentars-")   # the AI program starts in an empty folder
    out, err = [], []
    try:
        p = subprocess.Popen(argv, cwd=tmp, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, errors="replace", start_new_session=(os.name != "nt"))
        for stream, sink in ((p.stdout, out), (p.stderr, err)):
            threading.Thread(target=lambda s=stream, k=sink: k.extend(s), daemon=True).start()
        post(board + "/api/bridge/event", {"id": job["id"], "kind": "log", "text": name + " is working"})
        end = time.time() + 14 * 60
        while p.poll() is None and time.time() < end:
            time.sleep(2)
            if post(board + "/api/bridge/event", {"id": job["id"], "kind": "ping"}).get("cancel"):
                break
        if p.poll() is None:
            (os.killpg(p.pid, signal.SIGTERM) if os.name != "nt" else p.terminate())
            p.wait(5)
        time.sleep(0.3)
        text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", "".join(out)).strip()
        if p.returncode == 0 and text:
            post(board + "/api/bridge/done", {"id": job["id"], "ok": True, "text": text})
        else:
            tail = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", "".join(err) or text).strip()[-400:]
            post(board + "/api/bridge/done", {"id": job["id"], "ok": False, "text": "%s did not finish (exit %s). %s" % (name, p.returncode, tail)})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if len(sys.argv) > 3 and sys.argv[1] == "tool":
        return tool(sys.argv[2], sys.argv[3], sys.argv[4:])
    board = sys.argv[1] if len(sys.argv) > 1 else (open(SAVED).read().strip() if os.path.exists(SAVED) else "")
    if not board:
        sys.exit("Usage: python3 bridge.py http://<board address>")
    board = (board if "://" in board else "http://" + board).rstrip("/")
    found = [n for n in HARNESSES if shutil.which(n)]
    if not found:
        sys.exit("No AI program found. Install one of: " + ", ".join(HARNESSES))
    with open(SAVED, "w") as f:
        f.write(board)
    print("Board %s. Using: %s. Leave this window open; Ctrl+C to quit." % (board, ", ".join(found)))
    shown = True
    while True:
        try:
            job = post(board + "/api/bridge/poll", {"available": found}).get("job")
            shown = True
        except Exception as e:
            if shown:
                print("Cannot reach the board (%s). Retrying..." % e)
            shown = False
            time.sleep(3)
            continue
        if job:
            try:
                run_job(board, job, found)
            except Exception as e:
                try:
                    post(board + "/api/bridge/done", {"id": job["id"], "ok": False, "text": "bridge error: %s" % e})
                except Exception:
                    pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
