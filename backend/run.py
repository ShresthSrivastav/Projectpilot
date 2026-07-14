#!/usr/bin/env python3
import os
import socket
import uvicorn

DEFAULT_PORT = 5000
FALLBACK_PORT = 8080


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    port = int(os.getenv("PORT", str(DEFAULT_PORT)))

    if is_port_in_use(port):
        print(f"Port {port} is in use. Trying port {FALLBACK_PORT}...")
        port = FALLBACK_PORT

    if is_port_in_use(port):
        print(f"Port {port} is also in use. Please set PORT env var to a free port.")
        exit(1)

    print(f"Starting ProjectPilot backend on http://127.0.0.1:{port}")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
