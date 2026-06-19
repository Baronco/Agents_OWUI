"""Diagnose the OWUI socket.io websocket connection in isolation.

Run:  python scripts/diag_socket.py
Paste the full output. This goes under engine.io and uses websocket-client
directly so we see the REAL handshake error (status code / reason).
"""
import traceback
import websocket  # from websocket-client

WS_URL = "ws://localhost:3000/ws/socket.io/?transport=websocket&EIO=4"

print("websocket-client version:", getattr(websocket, "__version__", "?"))
print("=" * 60)


def try_ws(label, **kwargs):
    print(f"\n--- {label} ---")
    print("URL:", WS_URL, "kwargs:", kwargs)
    try:
        ws = websocket.create_connection(WS_URL, timeout=8, **kwargs)
        print("CONNECTED. First frame:", repr(ws.recv()[:200]))
        ws.close()
    except Exception as exc:
        print("FAILED:", repr(exc))
        traceback.print_exc()


try_ws("plain")
try_ws("with Origin", header=["Origin: http://localhost:3000"])
try_ws("with Origin + Host", header=["Origin: http://localhost:3000", "Host: localhost:3000"])
