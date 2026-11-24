"""Plain localStorage, first launch without a PIN, and one-time migration of encrypted PIN data."""
import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = os.environ.get("SS_BASE", "http://127.0.0.1:8776/index.html")
OUT = Path(os.environ.get("SS_OUT", "/workspace/switch-survey/verify/plain-storage"))
OUT.mkdir(parents=True, exist_ok=True)
WEBKIT = "/home/box/.cache/ms-playwright/webkit-2388/pw_run.sh"
# Test-only value used to seed and unlock a one-time migration. Never printed or stored by the app.
_OLD = os.environ.get("SS_TEST_OLD_PIN", "2468")
results = {"ok": True, "base": BASE, "checks": []}

def check(name, cond, detail=""):
    # Never include a PIN value in detail output.
    results["checks"].append({"name": name, "ok": bool(cond), "detail": str(detail)})
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not cond:
        results["ok"] = False
    return bool(cond)

async def shot(page, name):
    path = OUT / name
    await page.screenshot(path=str(path), full_page=True)
    return str(path)

async def enter_digits(page, digits):
    await page.wait_for_selector("#keypad")
    for d in digits:
        await page.click(f'.key[data-key="{d}"]')
    await page.click('.key[data-key="OK"]')

SEED_ENCRYPTED = """async (payload) => {
  const META_KEY = "switchSurvey.meta.v1";
  const DATA_KEY = "switchSurvey.data.v2";
  const ITERATIONS = 150000;
  const digits = payload.digits;
  const store = payload.store;
  const tab = payload.tab || "walk";
  function b64(buf) {
    const bytes = buf instanceof ArrayBuffer ? new Uint8Array(buf) : buf;
    let s = ""; bytes.forEach((b) => { s += String.fromCharCode(b); });
    return btoa(s);
  }
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(digits), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: ITERATIONS, hash: "SHA-256" },
    base,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
  async function encryptJson(obj) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(JSON.stringify(obj)));
    return { iv: b64(iv), ct: b64(ct) };
  }
  const checkVal = await encryptJson({ ok: true, kind: "ha-switch-survey" });
  const data = await encryptJson({ store, tab, draft: null, pendingMatch: null });
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
            "rooms": [
                {"id": "room_kit", "name": "Kitchen", "floor": "Main"},
                {"id": "room_off", "name": "Office", "floor": "Main"}
            ],
            "switches": [
                {"id": "sw_cans", "roomId": "room_kit", "floor": "Main", "load": "Can lights", "qualifier": "", "gangSize": 1, "gangPosition": 1, "loggedDumb": False, "note": "", "kindOverride": "", "fanType": "", "otherSpots": 0, "fixtureCount": 6},
                {"id": "sw_pend", "roomId": "room_off", "floor": "Main", "load": "Pendants", "qualifier": "", "gangSize": 1, "gangPosition": 1, "loggedDumb": False, "note": "", "kindOverride": "", "fanType": "", "otherSpots": 0, "fixtureCount": 3}
            ]
        }]
    }

async def storage_flags(page):
    return await page.evaluate("""() => ({
      meta: !!localStorage.getItem('switchSurvey.meta.v1'),
      data: !!localStorage.getItem('switchSurvey.data.v2')
    })""")

async def run():
    async with async_playwright() as p:
        browser = await p.webkit.launch(executable_path=WEBKIT)

        # 1. First launch: no PIN, survey form immediately, plain storage
        ctx = await browser.new_context(viewport={"width": 393, "height": 852}, color_scheme="dark", device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(BASE, wait_until="load")
        await page.wait_for_selector("[data-tab='walk']")
        body = await page.inner_text("body")
        check("first launch has no PIN screen",
              await page.locator("#keypad").count() == 0 and "Set a PIN" not in body and "Enter PIN" not in body and "Change PIN" not in body)
        check("first launch is the survey form", "Add a switch" in body and "Save switch" in body)
        src = await page.content()
        check("noindex kept", "noindex" in src)
        flags = await storage_flags(page)
        check("first launch writes plain storage, no encrypted copy", flags["data"] is True and flags["meta"] is False, flags)
        await shot(page, "393-dark-first-launch.png")

        # Save a switch, reload, still there, no unlock
        await page.select_option("select[data-field='room']", "Kitchen")
        await page.select_option("select[data-field='load']", "Can lights")
        await page.wait_for_timeout(80)
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await page.reload(wait_until="load")
        await page.wait_for_selector("[data-tab='walk']", timeout=4000)
        body = await page.inner_text("body")
        check("reload after save has no PIN screen", await page.locator("#keypad").count() == 0 and "Enter PIN" not in body)
        check("reload kept the kitchen cans entry", "kitchen cans" in body.lower() or "Kitchen cans" in body)
        await page.click("[data-tab='homes']")
        await page.wait_for_timeout(80)
        check("Homes tab has no PIN settings", "Change PIN" not in (await page.inner_text("body")) and "Forgot PIN" not in (await page.inner_text("body")))
        await ctx.close()

        # 2. Migration: seed encrypted v1 data, unlock once, never asked again
        ctx = await browser.new_context(viewport={"width": 393, "height": 852}, color_scheme="dark", device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(BASE, wait_until="load")
        await page.wait_for_selector("h1")
        seeded = await page.evaluate(SEED_ENCRYPTED, {"digits": _OLD, "store": sample_store(), "tab": "walk"})
        check("seeded encrypted survey", seeded is True)
        flags = await storage_flags(page)
        check("seed has encrypted meta and no plain data", flags["meta"] is True and flags["data"] is False, flags)
        await page.reload(wait_until="load")
        await page.wait_for_selector("#migrateUnlock")
        body = await page.inner_text("body")
        check("one-time move screen is shown for encrypted data",
              "Move your old survey (one time)" in body and "old 4–6 digit code is needed once" in body and "Skip, start fresh" in body and "Set a PIN" not in body and "Enter PIN" not in body)
        check("setup PIN screens are gone", "Set a PIN" not in body and "Confirm your new PIN" not in body)
        await shot(page, "393-dark-migrate-unlock.png")

        # Wrong value does not wipe the locked survey
        await enter_digits(page, "1111")
        await page.wait_for_timeout(400)
        body = await page.inner_text("body")
        check("wrong code keeps the move screen", "Move your old survey (one time)" in body and "That code did not work" in body)
        flags = await storage_flags(page)
        check("wrong code leaves encrypted data in place", flags["meta"] is True and flags["data"] is False, flags)

        await enter_digits(page, _OLD)
        await page.wait_for_selector("[data-tab='walk']", timeout=8000)
        body = await page.inner_text("body")
        check("unlock opens the survey with no PIN screens",
              await page.locator("#keypad").count() == 0 and "Move your old survey" not in body)
        await page.click("[data-tab='homes']")
        await page.wait_for_timeout(100)
        body = await page.inner_text("body")
        check("migrated home is kept", "Migrated House" in body)
        await page.click("text=Migrated House")
        await page.wait_for_timeout(150)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("migrated switches are kept", "Kitchen" in body and "Office" in body and "2 location" in body)
        rows = await page.eval_on_selector_all("table tbody tr", "els => els.map(tr => [...tr.children].map(td => td.innerText.trim()))")
        qty = {r[0]: int(r[1]) for r in rows if len(r) >= 2 and str(r[1]).isdigit()}
        check("migrated order still has 2 dimmers", qty.get("Smart dimmer") == 2, qty)
        flags = await storage_flags(page)
        check("encrypted copy is deleted after migrate", flags["meta"] is False and flags["data"] is True, flags)
        # JSON export still works after migration
        async with page.expect_download() as dl:
            await page.click("#exportJson")
        jp = OUT / "migrated-house.json"
        await (await dl.value).save_as(str(jp))
        data = json.loads(jp.read_text(encoding="utf-8"))
        homes = data.get("homes") or []
        h = next((x for x in homes if x.get("name") == "Migrated House"), None)
        check("JSON export is a Switch Survey backup", data.get("kind") == "ha-switch-survey" and h is not None)
        check("JSON export has both migrated switches", h is not None and len(h.get("switches") or []) == 2, len((h or {}).get("switches") or []))

        # Reload: never ask again, same homes
        await page.reload(wait_until="load")
        await page.wait_for_selector("[data-tab='walk']", timeout=4000)
        body = await page.inner_text("body")
        check("after migrate, reload has no unlock prompt",
              await page.locator("#migrateUnlock").count() == 0 and await page.locator("#keypad").count() == 0
              and "Move your old survey" not in body and "Enter PIN" not in body)
        await page.click("[data-tab='homes']")
        await page.wait_for_timeout(100)
        check("after migrate, reload kept the home", "Migrated House" in (await page.inner_text("body")))
        flags = await storage_flags(page)
        check("after reload, still plain only", flags["meta"] is False and flags["data"] is True, flags)

        leftovers = await page.evaluate("""() => {
          localStorage.removeItem('switchSurvey.meta.v1');
          localStorage.removeItem('switchSurvey.data.v2');
          return {
            meta: localStorage.getItem('switchSurvey.meta.v1'),
            data: localStorage.getItem('switchSurvey.data.v2')
          };
        }""")
        check("storage cleared", leftovers.get("meta") is None and leftovers.get("data") is None, leftovers)
        await ctx.close()
        await browser.close()

    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    failed = [c for c in results["checks"] if not c["ok"]]
    print("\nSUMMARY", "PASS" if results["ok"] else f"FAIL {len(failed)}", "of", len(results["checks"]))
    for c in failed:
        print(" -", c["name"], ":", str(c["detail"])[:400])
    sys.exit(0 if results["ok"] else 1)

asyncio.run(run())
