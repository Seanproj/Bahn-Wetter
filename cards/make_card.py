"""Render the 1080×1350 Instagram share card ("오늘의 Bahn-Wetter 예보") as PNG.

Serves the built site (site/dist) locally, opens #/card?date=YYYY-MM-DD in headless Chromium at
2× scale and screenshots the card. Build the site first: `cd site && npm run build`.

Usage:
    uv run --group cards python cards/make_card.py                 # today (Europe/Berlin)
    uv run --group cards python cards/make_card.py --date 2026-10-24
    CHROMIUM_PATH=/opt/pw-browsers/chromium uv run --group cards python cards/make_card.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import http.server
import os
import threading
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "site" / "dist"
OUT = ROOT / "cards" / "out"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def serve(directory: Path) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat())
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if not (DIST / "index.html").exists():
        raise SystemExit("site/dist missing — run `cd site && npm run build` first")

    out = (args.out or OUT / f"bahn-wetter-{args.date}.png").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    server = serve(DIST)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
            page = browser.new_page(viewport={"width": 540, "height": 675}, device_scale_factor=2,
                                    color_scheme="light", locale="ko-KR")
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/#/card?date={args.date}")
            card = page.wait_for_selector(".share-card")
            page.evaluate("document.fonts.ready")
            card.screenshot(path=str(out))
            browser.close()
        if errors:
            raise SystemExit(f"page errors: {errors}")
    finally:
        server.shutdown()
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
