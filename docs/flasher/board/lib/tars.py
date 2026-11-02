"""Helpers for programs: onboard RGB LED, OLED screen, BOOT button and ESP-NOW messages between boards.

    import tars
    tars.led(0, 40, 0)                 # onboard RGB LED (0-255 per colour)
    d = tars.oled()                    # ready OLED (framebuf API) or None if no screen answers
    d.fill(0); d.text("hi", 0, 0); d.show()
    b = tars.button()                  # BOOT button: b.value() == 0 while pressed
    tars.send("kitchen", "hello")      # text to another board by name ("all" = every board)
    inbox = tars.inbox()               # then inside your loop: msg = inbox.get(0) -> (sender, text) or None
    tars.peers()                       # names of the boards seen recently
    tars.localtime()                   # time tuple in the user's time zone (set with the set_timezone tool); tars.now() -> "HH:MM:SS"
    tars.sync_time()                   # sync the clock by NTP (done automatically at boot); returns True on success
"""
from core import hw, net


def led(r, g, b):
    return hw.led(r, g, b)


def oled():
    return hw.oled()


def button(pin=0):
    from machine import Pin
    return Pin(pin, Pin.IN, Pin.PULL_UP)


def send(to, text):
    return net.send_text_sync(to, str(text))


def inbox():
    return net.Inbox()


def peers():
    return [p["name"] for p in net.peers_info() if p["online"]]


def name():
    return net.name()


def sync_time(timeout=3):
    """Acerta o relógio da placa por NTP (fica em UTC). Devolve True se deu certo."""
    try:
        import ntptime
        ntptime.timeout = timeout
        ntptime.settime()
        return True
    except Exception:
        return False


def localtime():
    """Tupla de tempo no fuso configurado (Settings ou set_timezone). Antes do NTP o ano é 2000."""
    import time
    from core import config
    return time.gmtime(time.time() + config.get().get("tz_offset_min", 0) * 60)  # gmtime: a placa não tem fuso próprio, o offset vem da configuração


def now():
    t = localtime()
    return "%02d:%02d:%02d" % (t[3], t[4], t[5])
