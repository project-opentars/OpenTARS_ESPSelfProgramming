# Barramento de eventos que a página lê (GET /api/events?since=N). Seguro para threads: os programas publicam daqui também.
import _thread
from . import compat

_lock = _thread.allocate_lock()
_events = []
_next_id = 1
KEEP = 300


def emit(kind, **data):
    global _next_id
    with _lock:
        ev = {"id": _next_id, "kind": kind, "t": compat.ticks_ms()}
        ev.update(data)
        _next_id += 1
        _events.append(ev)
        if len(_events) > KEEP:
            del _events[: len(_events) - KEEP]
    return ev


def since(last_id, limit=100):
    with _lock:
        out = [e for e in _events if e["id"] > last_id]
    return out[:limit]


def last_id():
    with _lock:
        return _next_id - 1
