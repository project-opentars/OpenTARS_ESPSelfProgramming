# openTARS Self-Programming

> A simple lightweight ESP32 firmware that makes local and cloud AI models program your microcontroller natively. Ask for a code, and get it ready in seconds, already running on your board.

An AI agent that **lives inside a microcontroller** and programs it from your phone. You open the board's page, ask for something ("make the LED breathe", "show a spinning cube on the screen", "when the button on the kitchen board is pressed, beep here"), and the agent writes MicroPython, runs it on the board, reads the errors, fixes them and keeps what works as its own library.

Part of the [openTARS](https://github.com/project-opentars/openTars-lightweight-local-addon) family, with the same look and KIPP, the mascot.

- **Runs on the board.** The agent loop, the web page and the programs all run on an ESP32-S3 with MicroPython. No PC needed.
- **Any model.** Cloud APIs (Gemini, OpenAI, Groq, OpenRouter, any OpenAI-compatible endpoint) or **local models** on your computer through Ollama or LM Studio.
- **Self-programming.** Code is written and executed live, without reflashing. Reusable modules go to `/skills` and are offered to the agent in later conversations; facts go to its memory.
- **Boards talk to each other.** With ESP-NOW, boards find each other, exchange messages and run code on one another, without a router or a PC.
- **Convenient.** Phone-friendly page (English and Portuguese), file editor, program manager with logs, start-on-power-on, safe mode.

## Status

Early release (0.1.0). Tested on **one** ESP32-S3 board with Gemini as the model: page, agent loop, tool calling, programs, OLED and LED all work there. **ESP-NOW has only been tested with simulated boards** (two in-memory radios), not yet between two real boards. Local models (Ollama) are untested on hardware. Expect rough edges and please open issues.

## Hardware

Tested on an **ESP32-S3 with 8 MB octal PSRAM and 16 MB flash** (ESP32-S3-DevKitC-1 N16R8). PSRAM is required for the agent. Optional: an SSD1306 OLED (I2C) and the onboard RGB LED; the agent can use any sensor or module you wire, by writing the code for it.

## Quick start

1. Download MicroPython for your board (`ESP32_GENERIC_S3`, **SPIRAM_OCT** variant) from [micropython.org](https://micropython.org/download/ESP32_GENERIC_S3/) into `firmware/`.
2. Flash it (this **erases** the board): `tools/flash.sh /dev/ttyACM0`
3. Copy the system: `pip install mpremote` then `tools/deploy.sh /dev/ttyACM0`
4. On your phone, join the open Wi-Fi network **opentars-xxxx** and open **http://192.168.71.1** (the OLED, if connected, shows the address).
5. In **Settings**: pick your Wi-Fi, choose a model provider and paste your API key, then restart the board. It shows its new address on the OLED and on the serial console, and answers at `http://opentars-xxxx.local` on most networks.

### Local models (Ollama)

The board talks to Ollama on your computer over the network. Make Ollama listen on the network (`OLLAMA_HOST=0.0.0.0`, for example with `sudo systemctl edit ollama` and `Environment="OLLAMA_HOST=0.0.0.0"`), then in Settings choose **Ollama** and set the address to `http://<your computer's IP>:11434/v1`. Pick a model that handles tool calling well (Qwen3 4B or larger works; very small models struggle).

## How it works

```
phone / browser ──HTTP──▶ board (MicroPython)
                           ├─ web server + API (asyncio)
                           ├─ agent loop ──HTTPS──▶ model (cloud or Ollama on your LAN)
                           │    tools: run_code, start_program, write_file, remember, espnow_run, ...
                           ├─ programs (threads, stoppable through delay())
                           └─ ESP-NOW ◀────────▶ other boards
```

- `run_code` runs a snippet and returns what it printed and the error with the line number; long tasks become **programs** in the background. Programs must call `delay(ms)` inside loops; that is how they can be stopped.
- The agent can only write to `/skills`, `/programs`, `/data/files` and its notes; system files are protected so it cannot break itself. You can edit anything from the **Code** tab.
- Helper modules for programs: `tars` (LED, OLED, BOOT button, ESP-NOW messages) and `gfx` (3D wireframes, charts, bars), in `board/lib`.
- **Safe mode:** hold BOOT while powering on to skip programs that start automatically.

### ESP-NOW

Every board announces itself every 10 s. Boards on your Wi-Fi use the router's channel; boards without Wi-Fi use the channel set in Settings, so set it to the router's channel (shown in the **Boards** tab). Messages and remote code are split into 240-byte frames, so they can be up to ~60 KB.

## Troubleshooting

- **HTTP 429 (rate limit) and slow answers on free plans.** Free plans (Groq, Gemini) limit tokens per minute, and every tool round resends the conversation. The board **learns the provider's limit** from the first 429 (saved as *tokens per minute* in Settings), spaces its requests to stay under it, honours `Retry-After`, retries up to three times and keeps replies short (*max reply tokens*, 1500 by default, because some providers count it against your quota). The price is time: with ~8,000 tokens per minute an agent loop of 7 rounds takes a few minutes. A larger plan, or a provider without such a tight limit, makes it much faster.
- **A small model pastes code instead of running it, or answers with nothing.** The agent notices a code block without any tool call and asks the model to run it, asks for a summary after an empty answer (twice at most each) and retries malformed tool calls (`tool_use_failed`). If a model keeps failing, pick a larger one (for example `gpt-oss-120b` instead of `gpt-oss-20b`). "stop" and "pare tudo" never reach the model: the board stops every program by itself.
- **Wrong time.** The clock is synced by NTP at boot and is UTC. Set your time zone in **Settings** (UTC offset in hours) or just tell the agent where you live.
- **Opening the USB serial port restarts the board** (ESP32-S3 native USB). That is normal; the page shows the boot reason in `/api/status` and the last 30 boots are in `/data/boot.log`.

## Security

There is **no password**: anyone on the same Wi-Fi can open the page and run code on the board, and ESP-NOW traffic is not encrypted. Use it on a network you trust. HTTPS certificates are **not verified** on the board (MicroPython has no CA bundle here). Your API key is stored on the board in `/data/config.json`.

## Development

- `python3 tests/test_core.py` runs the core on your computer: web server, HTTP client, agent with a fake model, threads, tools and two simulated ESP-NOW boards.
- `python3 tests/test_robust.py` covers weak-model behaviour: code pasted instead of run, malformed tool calls, rate limits, retries, clock and time zone.
- `mpremote connect /dev/ttyACM0 run tests/smoke_board.py` runs a smoke test on the real board (fake model, threads, OLED, LED).
- `python3 tools/dev_server.py` serves the page and API on your computer with a fake model, to work on the interface.
- `python3 tools/build_web.py` compresses `web/` into `board/www/` (the deploy script does this for you).

## License

MIT. The SSD1306 driver follows the micropython-lib driver (MIT). IBM Plex fonts: SIL Open Font License (`web/fonts/OFL.txt`).
