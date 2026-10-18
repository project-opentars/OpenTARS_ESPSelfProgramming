"""Drawing helpers on top of any framebuf (for example tars.oled()): 3D wireframes, line charts, progress bars.

    import tars, gfx
    d = tars.oled(); g = gfx.Gfx(d)
    a = 0
    while True:
        d.fill(0); g.wire(gfx.CUBE, a * 0.7, a, a * 0.4); d.show(); a += 0.08; delay(20)
"""
import math

CUBE = ([(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)],
        [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)])
PYRAMID = ([(-1, 1, -1), (1, 1, -1), (1, 1, 1), (-1, 1, 1), (0, -1, 0)],
           [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4)])
OCTAHEDRON = ([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)],
              [(0, 2), (0, 3), (0, 4), (0, 5), (1, 2), (1, 3), (1, 4), (1, 5), (2, 4), (4, 3), (3, 5), (5, 2)])


class Gfx:
    def __init__(self, fb, width=128, height=64):
        self.fb, self.w, self.h = fb, width, height

    def wire(self, shape, ax=0.0, ay=0.0, az=0.0, scale=None, cx=None, cy=None, dist=6.0, c=1):
        """3D wireframe. Fits the screen while scale <= height/6 (the default)."""
        verts, edges = shape
        scale = scale or min(self.w, self.h) / 6
        cx = self.w / 2 if cx is None else cx
        cy = self.h / 2 if cy is None else cy
        sx, cx_, sy, cy_, sz, cz_ = math.sin(ax), math.cos(ax), math.sin(ay), math.cos(ay), math.sin(az), math.cos(az)
        pts = []
        for x, y, z in verts:
            y, z = y * cx_ - z * sx, y * sx + z * cx_
            x, z = x * cy_ + z * sy, -x * sy + z * cy_
            x, y = x * cz_ - y * sz, x * sz + y * cz_
            f = dist / (dist + z)
            pts.append((int(cx + x * scale * f), int(cy + y * scale * f)))
        for a, b in edges:
            self.fb.line(pts[a][0], pts[a][1], pts[b][0], pts[b][1], c)

    def plot(self, values, x, y, w, h, vmin=None, vmax=None, c=1):
        """Line chart of a list of numbers inside a frame."""
        if len(values) < 2:
            return
        lo = min(values) if vmin is None else vmin
        hi = max(values) if vmax is None else vmax
        if hi == lo:
            hi = lo + 1
        self.fb.rect(x, y, w, h, c)
        prev = None
        for i, v in enumerate(values):
            px = x + int(i * (w - 1) / (len(values) - 1))
            py = y + (h - 1) - int((v - lo) / (hi - lo) * (h - 1))
            if prev:
                self.fb.line(prev[0], prev[1], px, py, c)
            prev = (px, py)

    def bar(self, x, y, w, h, fraction, c=1):
        """Progress bar, fraction from 0 to 1."""
        self.fb.rect(x, y, w, h, c)
        f = max(0.0, min(1.0, fraction))
        self.fb.fill_rect(x + 2, y + 2, int((w - 4) * f), h - 4, c)

    def text_center(self, s, y, c=1):
        self.fb.text(s, (self.w - len(s) * 8) // 2, y, c)
