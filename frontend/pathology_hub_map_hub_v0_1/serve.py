#!/usr/bin/env python3
"""Static map hub server for Cloud Run."""
from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "public, max-age=300")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        if args and isinstance(args[0], int) and args[0] >= 400:
            super().log_message(fmt, *args)


def main() -> None:
    root = Path(__file__).resolve().parent / "www"
    os.chdir(root)
    port = int(os.environ.get("PORT", "8080"))
    print(f"serving map hub {root} on 0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
