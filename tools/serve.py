#!/usr/bin/env python3
"""Serve your page and its data folder on this computer, with the right headers (docs/HOSTING.md).

    python3 tools/serve.py --site /opt/geoforge-site            # then open http://127.0.0.1:8871/

The site folder holds the built page and the data:
    /opt/geoforge-site/index.html, assets/     <- the contents of app/dist/
    /opt/geoforge-site/data/                   <- written by csv_to_data.py and status_writer.py

It listens on 127.0.0.1 only: nothing outside this computer can reach it. The Cloudflare tunnel (cloudflared) runs on
the same computer and carries it to your public address. Headers it sends:
    data/      no caching, and Access-Control-Allow-Origin for the GeoForge Global Runs page
    assets/    cached for a year (the file names change on every build)
    the rest   no-cache (index.html always asks for the newest version)
Text files (.json, .js, .css, .html) are sent gzip-compressed to browsers that accept it: cells.json shrinks
about 8 times, which matters a lot through a slow tunnel. Compressed copies are kept in memory (at most 200 MB; a
single copy over 50 MB is not kept) and made again whenever a file changes.
A browser that accepts neither gzip nor the plain file (Accept-Encoding: identity;q=0 without gzip) gets 406.
Folder listings, half-written *.tmp files, hidden names (starting with '.', e.g. data/.export.lock) and anything whose
real place (after following links) is outside the site folder are never served. So data/ must be a real folder
inside the site folder, not a link to another disk. Only the Python standard library is used.
"""
import argparse
import gzip
import io
import os
import sys
import threading
from collections import OrderedDict
from email.utils import formatdate
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    origin = "https://geoforgehhu.com"
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".json": "application/json; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                      ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8"}

    def _rel(self):
        """The asked-for file relative to the site folder, cleaned the same way the file is looked up
        (so tricks like /data/x.tmp/. or //data/ are judged on the real file)."""
        rel = os.path.relpath(self.translate_path(self.path), self.directory).replace(os.sep, "/")
        return "" if rel == "." else rel

    def send_response(self, code, message=None):
        self._code = code
        super().send_response(code, message)

    def _resolve(self):
        """The real file to send (links followed, a folder's index.html), or None when it must not be served:
        outside the real site folder, a *.tmp file, a hidden name (.export.lock, .history.json) or not a file."""
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            idx = [os.path.join(path, n) for n in ("index.html", "index.htm") if os.path.exists(os.path.join(path, n))]
            if not idx:
                return None
            path = idx[0]
        root = os.path.realpath(self.directory)
        real = os.path.realpath(path)
        if not (real.startswith(root + os.sep) and os.path.isfile(real)):
            return None
        rel = os.path.relpath(real, root).split(os.sep)
        asked = self._rel().split("/")
        if any(x.startswith(".") for x in rel + asked) or real.endswith(".tmp") or path.endswith(".tmp"):
            return None
        return real

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path) and not self.path.split("?", 1)[0].split("#", 1)[0].endswith("/"):
            return super().send_head()          # the standard "add the slash" redirect; nothing is read
        real = self._resolve()
        if real is None:
            self.send_error(404); return None
        enc = self._encodings()
        gzip_ok, plain_ok = enc
        if gzip_ok and real.endswith(self.GZ_TYPES) and "Range" not in self.headers:
            gz = self._gzip_head(real, force=not plain_ok)
            if gz is not None:
                return gz
        if not plain_ok:
            self.send_error(406, "Not Acceptable", "this file is sent plain or gzip-compressed"); return None
        try:
            f = open(real, "rb")                # the resolved file itself, never the asked-for name again
        except OSError:
            self.send_error(404); return None
        try:
            st = os.fstat(f.fileno())
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(real))
            self.send_header("Content-Length", str(st.st_size))
            self.send_header("Last-Modified", formatdate(st.st_mtime, usegmt=True))
            self.end_headers()
            return f
        except Exception:
            f.close()
            raise

    # ---- gzip: compressed copy of a text file, made once per file version and kept in memory ----
    _gz_cache = OrderedDict()                  # file version -> gzip bytes
    _gz_busy = {}                              # file version -> [Event, bytes or None], while one thread compresses it
    _gz_bytes = 0
    _gz_lock = threading.Lock()
    GZ_MAX = 200 * 1024 * 1024
    GZ_ONE_MAX = GZ_MAX // 4                   # a bigger compressed copy is sent but not kept
    GZ_TYPES = (".json", ".js", ".css", ".html")
    GZ_WAIT_S = 60

    def _encodings(self):
        """(gzip acceptable, plain acceptable) from Accept-Encoding with q-values. No header: plain only.
        'gzip;q=0' means no gzip; 'identity;q=0' (or '*;q=0' without naming identity) means no plain."""
        q = {}
        header = self.headers.get("Accept-Encoding")
        if header is None:
            return False, True
        for part in header.split(","):
            bits = [b.strip() for b in part.split(";")]
            name, val = bits[0].lower(), 1.0
            if not name:
                continue
            for b in bits[1:]:
                if b.lower().startswith("q="):
                    try:
                        val = float(b[2:])
                    except ValueError:
                        val = 0.0
            q[name] = val
        star = q.get("*")
        g = q.get("gzip", star)
        i = q.get("identity", star if star is not None and star == 0 else None)
        return (g is not None and g > 0), (i is None or i > 0)

    def _gzip_head(self, real, force=False):
        """Send headers for a gzip copy and return it as a file, or None to send the plain file instead.
        Small files are sent plain unless plain is not acceptable (force)."""
        try:
            with open(real, "rb") as f:            # files are replaced by rename, so this read is one whole version
                st = os.fstat(f.fileno())
                if st.st_size < 1024 and not force:
                    return None
                key = (real, st.st_dev, st.st_ino, st.st_mtime_ns, st.st_ctime_ns, st.st_size)
                body = self._gz_get(key, f)
        except OSError:
            return None
        if body is None:                           # waited too long for another thread: send it plain
            return None
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(real))
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self._vary_sent = True
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Last-Modified", formatdate(st.st_mtime, usegmt=True))
        self.end_headers()
        return io.BytesIO(body)

    def _gz_get(self, key, f):
        """The compressed bytes of this file version. Only one thread compresses a version; the others wait for
        that same result (also when it is too big to keep). None after waiting GZ_WAIT_S in vain."""
        with self._gz_lock:
            body = self._gz_cache.get(key)
            if body is not None:
                self._gz_cache.move_to_end(key)
                return body
            slot = self._gz_busy.get(key)
            maker = slot is None
            if maker:
                slot = self._gz_busy[key] = [threading.Event(), None]
        if not maker:
            slot[0].wait(self.GZ_WAIT_S)
            return slot[1]                          # the maker's bytes, or None (timeout or the maker failed)
        try:
            body = gzip.compress(f.read(), compresslevel=6, mtime=0)
            slot[1] = body
            if len(body) <= self.GZ_ONE_MAX:
                with self._gz_lock:
                    for k in [k for k in self._gz_cache if k[0] == key[0]]:     # older versions of this file
                        Handler._gz_bytes -= len(self._gz_cache.pop(k))
                    self._gz_cache[key] = body
                    Handler._gz_bytes += len(body)
                    while Handler._gz_bytes > self.GZ_MAX and self._gz_cache:
                        Handler._gz_bytes -= len(self._gz_cache.popitem(last=False)[1])
            return body
        finally:
            with self._gz_lock:
                self._gz_busy.pop(key, None)
            slot[0].set()

    def list_directory(self, path):            # never show what is in a folder
        self.send_error(404); return None

    def end_headers(self):
        p = self._rel()
        if p == "data" or p.startswith("data/"):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", self.origin)
        elif p.startswith("assets/") and getattr(self, "_code", 0) == 200:   # never cache a missing file for a year
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        if p.endswith(self.GZ_TYPES) and not getattr(self, "_vary_sent", False):
            self.send_header("Vary", "Accept-Encoding")     # the same address can come plain or compressed
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, fmt, *args):         # one short line per request, without the visitor's address
        sys.stderr.write(f"{self.log_date_time_string()} {fmt % args}\n")


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--site", required=True, help="folder with index.html, assets/ and data/")
    a.add_argument("--port", type=int, default=8871)
    a.add_argument("--origin", default="https://geoforgehhu.com", help="the page allowed to read data/ (leave as is)")
    args = a.parse_args()
    site = Path(args.site).resolve()
    if not (site / "index.html").is_file():
        sys.exit(f"{site}: no index.html. Copy the contents of app/dist/ (after npm run build) into it")
    if not (site / "data").is_dir():
        print(f"note: {site}/data does not exist yet; the page shows an error until your data are written", file=sys.stderr)
    Handler.origin = args.origin
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(site)))
    print(f"serving {site} at http://127.0.0.1:{args.port}/ (this computer only; Ctrl+C stops it)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
