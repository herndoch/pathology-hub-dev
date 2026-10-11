#!/usr/bin/env python3
"""Serve the shareable map package using only Python's standard library."""
from __future__ import annotations
import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import os

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        redirects = {"/textbooks": "/content/?source=textbooks", "/textbooks/": "/content/?source=textbooks",
                     "/journals": "/content/?source=references", "/journals/": "/content/?source=references",
                     "/app": "https://chat.pathologynotebook.com/", "/app/": "https://chat.pathologynotebook.com/"}
        if path in redirects:
            self.send_response(302)
            self.send_header("Location", redirects[path])
            self.end_headers()
            return
        if path in ("/health", "/healthz"):
            body = json.dumps({"status": "ok", "service": "pathology-hub-map"}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            if self.command != "HEAD": self.wfile.write(body)
            return
        if any(p.startswith(".") for p in path.split("/") if p) or not (
            path in ("/", "/index.html", "/content", "/lectures", "/videos") or
            path.startswith(("/static/", "/content/", "/lectures/", "/videos/"))
        ):
            self.send_error(404); return
        super().do_GET()

    def do_HEAD(self):
        # Use the same path policy without writing a response body.
        # Headers must still reach the socket; SimpleHTTPRequestHandler's
        # copyfile is the only static-body writer.
        self._head_only = True
        try: self.do_GET()
        finally: self._head_only = False

    def copyfile(self, source, outputfile):
        if not getattr(self, "_head_only", False):
            super().copyfile(source, outputfile)

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache" if self.path.split("?")[0].endswith(("/", ".html")) else "public, max-age=300")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8770")))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if (root / "www").is_dir(): root = root / "www"
    print(f"Pathology Hub: http://{args.host}:{args.port}/", flush=True)
    ThreadingHTTPServer((args.host, args.port), partial(Handler, directory=str(root))).serve_forever()

if __name__ == "__main__":
    main()
