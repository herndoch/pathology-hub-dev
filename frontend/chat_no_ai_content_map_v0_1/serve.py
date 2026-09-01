# Minimal static file server for Cloud Run (PORT from env).
from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        # Keep Cloud Run logs readable; still emit errors.
        if args and isinstance(args[0], int) and args[0] >= 400:
            super().log_message(fmt, *args)


def main() -> None:
    root = Path(__file__).resolve().parent / "www"
    os.chdir(root)
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), QuietHandler)
    print(f"serving {root} on 0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
