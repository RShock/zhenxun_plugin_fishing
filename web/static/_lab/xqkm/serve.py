#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Serve the S2 猫猫挖矿 web demo on port 4160 (optional). Prefer 4159/_lab/xqkm/."""

from __future__ import annotations

import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = 4160
ROOT = os.path.dirname(os.path.abspath(__file__))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[4160] " + (fmt % args) + "\n")


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"猫猫挖矿 Demo: http://127.0.0.1:{PORT}/")
    print(f"Serving: {ROOT}")
    print("Prefer: http://127.0.0.1:4159/_lab/xqkm/index.html")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
