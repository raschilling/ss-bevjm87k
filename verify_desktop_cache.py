"""Desktop Chromium, WebKit, and Firefox: plain URL, encrypted-data migration, and stale-cache update."""
import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = os.environ.get("SS_BASE", "http://127.0.0.1:8776/index.html")
OUT = Path(os.environ.get("SS_OUT", "/workspace/switch-survey/verify/desktop-cache"))
OUT.mkdir(parents=True, exist_ok=True)
ROOT = Path(__file__).resolve().parent
CURRENT_HTML = (ROOT / "index.html").read_text(encoding="utf-8")
OLD_PIN_HTML = (ROOT / "verify/fixtures/old-pin-index.html").read_text(encoding="utf-8")
WEBKIT = "/home/box/.cache/ms-playwright/webkit-2388/pw_run.sh"
APP_VERSION = "2026-11-24j"
_OLD = os.environ.get("SS_TEST_OLD_PIN", "2468")
results = {"ok": True, "base": BASE, "checks": []}
DESKTOP = {"width": 1440, "height": 900}

def check(name, cond, detail=""):
    results["checks"].append({"name": name, "ok": bool(cond), "detail": str(detail)})
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not cond:
        results["ok"] = False
    return bool(cond)

async def shot(page, name):
    path = OUT / name
    await page.screenshot(path=str(path), full_page=True)
    return str(path)

def origin_from_base(base):
    # http://127.0.0.1:8776/index.html or https://host/ss-bevjm87k/ or with ?v=
    from urllib.parse import urlparse, urlunparse
    u = urlparse(base)
    path = u.path
    if path.endswith("/index.html"):
        path = path[: -len("index.html")] or "/"
    if not path.endswith("/"):
        path = path + "/"
    # plain URL with no query
    return urlunparse((u.scheme, u.netloc, path, "", "", ""))

PLAIN = origin_from_base(BASE)

async def safe_goto(page, url):
    """Load url, retrying if a service worker or version check aborts the first navigation."""
    last = None
    for _ in range(3):
        try:
            await page.goto(url, wait_until="load")
            await page.wait_for_timeout(200)
            return
        except Exception as e:
            last = e
            await page.wait_for_timeout(300)
    raise last

SEED_ENCRYPTED = """async (payload) => {
  const META_KEY = "switchSurvey.meta.v1";
  const DATA_KEY = "switchSurvey.data.v2";
  const ITERATIONS = 150000;
  const digits = payload.digits;
  const store = payload.store;
  function b64(buf) {
    const bytes = buf instanceof ArrayBuffer ? new Uint8Array(buf) : buf;
    let s = ""; bytes.forEach((b) => { s += String.fromCharCode(b); });
    return btoa(s);
  }
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(digits), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: ITERATIONS, hash: "SHA-256" },
    base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]
  );
  async function encryptJson(obj) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(JSON.stringify(obj)));
    return { iv: b64(iv), ct: b64(ct) };
  }
  const checkVal = await encryptJson({ ok: true, kind: "ha-switch-survey" });
  const data = await encryptJson({ store, tab: "walk", draft: null, pendingMatch: null });
  localStorage.setItem(META_KEY, JSON.stringify({ v: 1, salt: b64(salt), iterations: ITERATIONS, check: checkVal, data }));
  localStorage.removeItem(DATA_KEY);
  return true;
}"""

def sample_store():
    return {
        "version": 1,
        "kind": "ha-switch-survey",
        "activeHomeId": "home_migrated1",
        "homes": [{
            "id": "home_migrated1",
            "name": "Migrated House",
            "brand": "undecided",
            "neutrals": "yes",
            "isExample": False,
            "rooms": [{"id": "room_kit", "name": "Kitchen", "floor": "Main"}],
            "switches": [{"id": "sw_cans", "roomId": "room_kit", "floor": "Main", "load": "Can lights", "qualifier": "", "gangSize": 1, "gangPosition": 1, "loggedDumb": False, "note": "", "kindOverride": "", "fanType": "", "otherSpots": 0, "fixtureCount": 4}]
        }]
    }

async def enter_digits(page, digits):
    await page.wait_for_selector("#keypad")
    for d in digits:
        await page.click(f'.key[data-key="{d}"]')
    await page.click('.key[data-key="OK"]')

async def launch(p, name):
    if name == "webkit":
        return await p.webkit.launch(executable_path=WEBKIT)
    if name == "chromium":
        return await p.chromium.launch(args=["--no-sandbox", "--disable-gpu"])
    if name == "firefox":
        return await p.firefox.launch()
    raise ValueError(name)

async def fresh_plain(browser, name, color_scheme="dark", viewport=None):
    vp = viewport or DESKTOP
    ctx = await browser.new_context(viewport=vp, color_scheme=color_scheme, device_scale_factor=1)
    page = await ctx.new_page()
    await safe_goto(page, PLAIN)
    await page.wait_for_selector("[data-tab='walk']", timeout=8000)
    body = await page.inner_text("body")
    html = await page.content()
    tag = f"{name} {color_scheme} {vp['width']}"
    check(f"{tag} plain URL has no PIN screen",
          await page.locator("#keypad").count() == 0 and "Set a PIN" not in body and "Enter PIN" not in body and "Change PIN" not in body)
    check(f"{tag} plain URL is the survey form", "Add a switch" in body and "Save switch" in body)
    check(f"{tag} Keep as is (not smart) on form", "Keep as is (not smart)" in body and "Regular switch" not in body)
    check(f"{tag} serves current ss-version", f'content="{APP_VERSION}"' in html or APP_VERSION in html, APP_VERSION)
    await shot(page, f"{vp['width']}-{color_scheme}-{name}-fresh.png")
    await ctx.close()

async def encrypted_migrate(browser, name, color_scheme="dark", viewport=None, complete=False):
    vp = viewport or DESKTOP
    ctx = await browser.new_context(viewport=vp, color_scheme=color_scheme, device_scale_factor=1)
    page = await ctx.new_page()
    await safe_goto(page, PLAIN)
    await page.wait_for_selector("h1")
    await page.evaluate(SEED_ENCRYPTED, {"digits": _OLD, "store": sample_store()})
    await safe_goto(page, PLAIN)
    await page.wait_for_selector("#migrateUnlock", timeout=8000)
    body = await page.inner_text("body")
    tag = f"{name} {color_scheme} {vp['width']}"
    check(f"{tag} encrypted data shows one-time move, not a PIN setup",
          "Move your old survey (one time)" in body and "Skip, start fresh" in body
          and "old 4–6 digit code is needed once" in body
          and "Set a PIN" not in body and "Enter PIN" not in body and "Change PIN" not in body)
    await shot(page, f"{vp['width']}-{color_scheme}-{name}-migrate.png")
    if complete:
        await enter_digits(page, _OLD)
        await page.wait_for_selector("[data-tab='walk']", timeout=8000)
        await page.click("[data-tab='homes']")
        await page.wait_for_timeout(100)
        check(f"{tag} migrate kept the home", "Migrated House" in (await page.inner_text("body")))
    else:
        # Skip path is visible; cancel after opening confirm so we don't wipe mid-suite unless we want to
        await page.click("#migrateSkip")
        await page.wait_for_timeout(80)
        body = await page.inner_text("body")
        check(f"{tag} Skip, start fresh asks before erasing",
              "Starting fresh erases the locked survey" in body and "JSON backup" in body)
        await page.click("#migrateSkipCancel")
        await page.wait_for_timeout(80)
        check(f"{tag} cancel returns to the move screen",
              "Move your old survey (one time)" in (await page.inner_text("body")))
    await ctx.close()

async def stale_version_reloads(browser, name):
    """A cached copy of the current app with an old ss-version should reload to the network copy."""
    stale = CURRENT_HTML.replace(APP_VERSION, "old-cached")
    ctx = await browser.new_context(viewport=DESKTOP, color_scheme="dark", device_scale_factor=1)
    page = await ctx.new_page()

    async def handler(route):
        req = route.request
        url = req.url
        # Version check or post-reload navigation with ssver=
        if "ssver=" in url:
            await route.fulfill(status=200, content_type="text/html; charset=utf-8", body=CURRENT_HTML)
            return
        if req.resource_type == "document" or (req.method == "GET" and "text/html" in (req.headers.get("accept") or "")):
            await route.fulfill(status=200, content_type="text/html; charset=utf-8", body=stale)
            return
        await route.fallback()

    await page.route("**/*", handler)
    await page.goto(PLAIN, wait_until="load")
    # Should replace to ?ssver=APP_VERSION and then show the survey
    try:
        await page.wait_for_selector("[data-tab='walk']", timeout=10000)
        recovered = True
        body = await page.inner_text("body")
    except Exception:
        recovered = False
        body = await page.inner_text("body")
    check(f"{name} stale cached version reloads to the survey",
          recovered and "Add a switch" in body and "Set a PIN" not in body and "Enter PIN" not in body,
          (body or "")[:200])
    await page.unroute("**/*")
    await ctx.close()

async def cached_old_pin_then_network(browser, name):
    """An old Set-a-PIN HTML in cache still shows a PIN until the network copy is fetched."""
    ctx = await browser.new_context(viewport=DESKTOP, color_scheme="dark", device_scale_factor=1)
    page = await ctx.new_page()
    served_old = {"n": 0}

    async def handler(route):
        req = route.request
        if req.resource_type == "document" or (req.method == "GET" and "text/html" in (req.headers.get("accept") or "") and "ssver=" not in req.url):
            served_old["n"] += 1
            await route.fulfill(status=200, content_type="text/html; charset=utf-8", body=OLD_PIN_HTML)
            return
        await route.fallback()

    await page.route("**/*", handler)
    await page.goto(PLAIN, wait_until="load")
    body = await page.inner_text("body")
    check(f"{name} cached old HTML still shows Set a PIN",
          "Set a PIN" in body and await page.locator("[data-tab='walk']").count() == 0)
    await page.unroute("**/*")
    # Now load the real plain URL (network / current file)
    await safe_goto(page, PLAIN)
    await page.wait_for_selector("[data-tab='walk']", timeout=8000)
    body = await page.inner_text("body")
    check(f"{name} after cache drop, plain URL is the new survey",
          "Add a switch" in body and "Keep as is (not smart)" in body and "Set a PIN" not in body and "Enter PIN" not in body)
    await ctx.close()

async def run():
    browsers = ["chromium", "webkit", "firefox"]
    async with async_playwright() as p:
        # 393 dark/light migrate + fresh on webkit (phone-sized, as before)
        webkit_browser = await launch(p, "webkit")
        await fresh_plain(webkit_browser, "webkit", "dark", {"width": 393, "height": 852})
        await fresh_plain(webkit_browser, "webkit", "light", {"width": 393, "height": 852})
        await encrypted_migrate(webkit_browser, "webkit", "dark", {"width": 393, "height": 852}, complete=True)
        await encrypted_migrate(webkit_browser, "webkit", "light", {"width": 393, "height": 852}, complete=False)
        await webkit_browser.close()

        for name in browsers:
            browser = await launch(p, name)
            await fresh_plain(browser, name, "dark")
            await fresh_plain(browser, name, "light")
            await encrypted_migrate(browser, name, "dark", complete=(name == "chromium"))
            await stale_version_reloads(browser, name)
            await cached_old_pin_then_network(browser, name)
            await browser.close()

    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    failed = [c for c in results["checks"] if not c["ok"]]
    print("\nSUMMARY", "PASS" if results["ok"] else f"FAIL {len(failed)}", "of", len(results["checks"]))
    for c in failed:
        print(" -", c["name"], ":", str(c["detail"])[:400])
    sys.exit(0 if results["ok"] else 1)

asyncio.run(run())
