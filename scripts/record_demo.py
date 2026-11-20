"""Record the portfolio video (demo.mp4, 1080p60) and 4 screenshots (docs/screenshots/) from the local emulator.

Needs the server running on 127.0.0.1:8092 with a fresh DB, e.g.:
    DB_PATH=/tmp/wa_demo/agent.db .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8092
Then:
    .venv/bin/python scripts/record_demo.py
Uses the installed Google Chrome (channel="chrome") and records frames through the Chrome
DevTools screencast + system ffmpeg, so no Playwright browser/ffmpeg download is needed.
"""
from __future__ import annotations

import base64
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:8092/demo/?theme=dark"  # Demo Showcase kit: light or dark
W, H = 1920, 1080
SHOTS = ROOT / "docs" / "screenshots"



def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="wavid_"))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--disable-gpu-vsync", "--disable-frame-rate-limit"])
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page = ctx.new_page()
        frames: list[tuple[float, Path]] = []
        cdp = ctx.new_cdp_session(page)

        def on_frame(ev):
            f = tmp / f"f{len(frames):05d}.jpg"
            f.write_bytes(base64.b64decode(ev["data"]))
            frames.append((ev["metadata"]["timestamp"], f))
            try:
                cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            except Exception:
                pass

        cdp.on("Page.screencastFrame", on_frame)
        page.goto(URL)
        page.wait_for_function("window.demoReady === true")
        page.wait_for_timeout(600)
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 95, "maxWidth": W, "maxHeight": H,
                                          "everyNthFrame": 1})
        page.wait_for_timeout(900)

        client = page.locator("#p-client")
        manager = page.locator("#p-manager")

        def shot(name):
            page.screenshot(path=str(SHOTS / name))

        def step(n):
            page.evaluate(f"window.demo.setStep({n})")

        def click(loc, pause=350):
            """No cursor in the video: soft tap ripple on the element, then a real DOM click."""
            loc.evaluate("el => window.demo.tap(el)")
            page.wait_for_timeout(220)
            loc.evaluate("el => el.click()")
            page.wait_for_timeout(pause)

        def type_send(phone, text, delay=38):
            inp = phone.locator("input")
            inp.evaluate("el => el.focus()")
            page.wait_for_timeout(150)
            inp.press_sequentially(text, delay=delay)
            page.wait_for_timeout(250)
            click(phone.locator(".ds-composer__send"), 100)

        def settle(extra=1200):
            page.wait_for_timeout(300)
            page.evaluate("window.demo.idle()")
            page.wait_for_timeout(extra)

        SHOTS.mkdir(parents=True, exist_ok=True)
        page.set_default_timeout(15000)
        try:
            # 1. answer from the price list, with the source + AI disclosure
            step(1)
            type_send(client, "Hi! How much is the German evening course?")
            settle(3200)
            shot("01-answer-with-source.png")

            # 2. PDF terms, in German
            step(2)
            type_send(client, "Bis wann kann ich kostenlos stornieren?")
            settle(3000)

            # 3. not in the documents -> honest hand-over, manager alerted
            step(3)
            type_send(client, "Вы помогаете с визой?")
            settle(2400)
            shot("02-hand-over.png")

            # 4. lead qualification
            step(4)
            type_send(client, "I'd like to sign up for the B1 evening course")
            settle(900)
            type_send(client, "Anna", 70)
            settle(900)
            type_send(client, "around 600 €", 60)
            settle(2400)
            shot("03-hot-lead.png")

            # 5. manager replies from the alert
            step(5)
            click(manager.locator(".reply-btn .ds-kb__btn").last, 500)
            manager.locator("input").press_sequentially("Hi Anna, Lena here! Your seat in the B1 evening group from 12 January is reserved.", delay=26)
            page.wait_for_timeout(250)
            click(manager.locator(".ds-composer__send"), 100)
            settle(2600)

            page.evaluate("window.demo.endCard()")
            page.wait_for_timeout(5200)
            shot("04-end-card.png")

        except Exception:
            page.screenshot(path=str(tmp.parent / 'record_fail.png'))
            print('FAILED, screenshot:', tmp.parent / 'record_fail.png')
            raise
        end_ts = time.time()
        cdp.send("Page.stopScreencast")
        page.wait_for_timeout(300)
        ctx.close()
        browser.close()

    # screencast frames come only when the page changes, at irregular times -> resample them
    # ourselves onto an exact 60 fps grid (latest frame at each tick) and pipe to ffmpeg
    out = ROOT / "demo.mp4"
    fps = 60
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps),
                             "-c:v", "mjpeg", "-i", "-", "-vf", f"scale={W}:{H}:flags=lanczos,format=yuv420p",
                             "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-r", str(fps),
                             "-movflags", "+faststart", "-an", str(out)], stdin=subprocess.PIPE)
    t0, j = frames[0][0], 0
    for k in range(int((end_ts - t0) * fps) + 1):
        t = t0 + k / fps
        while j + 1 < len(frames) and frames[j + 1][0] <= t + 1e-4:
            j += 1
        gap = frames[j + 1][0] - frames[j][0] if j + 1 < len(frames) else 0
        if 1.5 / fps < gap < 4.5 / fps and t - frames[j][0] >= 0.5 / fps:
            # Chrome dropped frames in the middle of an animation: fill the hole with a weighted
            # blend of the neighbours instead of holding the old frame (no visible hitch)
            w = (t - frames[j][0]) / gap
            proc.stdin.write(subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(frames[j][1]), "-i", str(frames[j + 1][1]), "-filter_complex",
                 f"blend=all_expr='A*{1 - w:.3f}+B*{w:.3f}'", "-q:v", "1", "-f", "mjpeg", "-"], capture_output=True, check=True).stdout)
            continue
        proc.stdin.write(frames[j][1].read_bytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    shutil.rmtree(tmp, ignore_errors=True)
    print("saved", out)


if __name__ == "__main__":
    sys.exit(main())
