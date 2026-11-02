# Acesso ao hardware da placa usado pelo sistema: LED RGB e a tela OLED (só se estiver ligada).
from . import config

_np = None


def led(r, g, b):
    global _np
    try:
        if _np is None:
            import neopixel
            from machine import Pin
            _np = neopixel.NeoPixel(Pin(config.get().get("rgb_led_pin", 48)), 1)
        _np[0] = (int(r), int(g), int(b))
        _np.write()
        return True
    except Exception:
        return False


def oled():
    """Abre a OLED configurada (SSD1306 por I2C). Devolve None se não houver tela respondendo."""
    try:
        from machine import I2C, Pin
        import ssd1306
    except ImportError:
        return None
    o = config.get().get("oled") or {}
    try:
        i2c = I2C(0, sda=Pin(o.get("sda", 9)), scl=Pin(o.get("scl", 8)), freq=400000)
        if o.get("addr", 60) not in i2c.scan():
            return None
        for _ in range(3):  # a primeira escrita depois de ligar o barramento às vezes falha
            try:
                return ssd1306.SSD1306_I2C(o.get("width", 128), o.get("height", 64), i2c, o.get("addr", 60))
            except OSError:
                import time
                time.sleep_ms(100)
    except Exception:
        return None
    return None


def show_boot_info(st):
    """Mostra na OLED (se houver) como achar a placa: rede e endereço."""
    d = oled()
    if not d:
        return
    d.fill(0)
    d.text("openTARS", 0, 0)
    d.text("Self-Programming", 0, 10)
    if st.get("mode") == "ap":
        d.text("Wi-Fi: " + st.get("ssid", "")[:13], 0, 28)
        d.text("open http://", 0, 40)
        d.text(st.get("ip", ""), 0, 50)
    else:
        d.text(st.get("name", "")[:16], 0, 28)
        d.text("http://", 0, 40)
        d.text(st.get("ip", ""), 0, 50)
    d.show()
