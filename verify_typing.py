"""Type a full sentence into every text field and confirm focus and value stay."""
import asyncio, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = os.environ.get("SS_BASE", "http://127.0.0.1:8779/index.html")
OUT = Path(os.environ.get("SS_OUT", "/workspace/switch-survey/verify/typing"))
OUT.mkdir(parents=True, exist_ok=True)
WEBKIT = "/home/box/.cache/ms-playwright/webkit-2388/pw_run.sh"
results = {"ok": True, "checks": []}

def check(name, cond, detail=""):
    results["checks"].append({"name": name, "ok": bool(cond), "detail": str(detail)})
    print(("PASS" if cond else "FAIL"), name + (f" — {detail}" if detail else ""))
    if not cond:
        results["ok"] = False

async def shot(page, name):
    path = OUT / name
    await page.screenshot(path=str(path), full_page=True)
    return str(path)

async def type_sentence(page, locator, sentence, field_label, focus_check):
    await locator.click()
    await page.wait_for_timeout(80)
    # Clear any existing value without replacing the node
    await locator.fill("")
    await locator.click()
    await locator.press_sequentially(sentence, delay=30)
    focused = await page.evaluate(focus_check)
    value = await locator.input_value()
    check(f"{field_label} keeps focus after a full sentence", focused, f"active={await page.evaluate('() => document.activeElement && (document.activeElement.id || document.activeElement.getAttribute(\"data-field\") || document.activeElement.tagName)')}")
    check(f"{field_label} keeps the full typed value", value == sentence, repr(value))
    # mid-string sanity: value length equals sentence, no dropped letters
    check(f"{field_label} did not drop letters", len(value) == len(sentence), f"got {len(value)} expected {len(sentence)}")

async def run():
    note = "Check the jumper at this box tonight."
    room = "Mudroom by the side door."
    load = "Accent lights over the sink."
    house = "Lakefront cottage on Maple."
    new_house = "Garage apartment out back."
    fixtures = "12"

    async with async_playwright() as p:
        browser = await p.webkit.launch(executable_path=WEBKIT)
        ctx = await browser.new_context(viewport={"width": 393, "height": 852}, color_scheme="dark", device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(BASE, wait_until="load")
        await page.wait_for_selector("#loadQuery", timeout=15000)
        ver = await page.evaluate("() => (window.__ss && __ss.appVersion && __ss.appVersion()) || (document.querySelector('meta[name=\\'ss-version\\']') || {}).content")
        check("version is 2026-11-24k", ver == "2026-11-24k", ver)

        # What it controls
        load_el = page.locator("#loadQuery")
        await type_sentence(page, load_el, load, "What it controls",
                            "() => document.activeElement && document.activeElement.id === 'loadQuery'")
        await shot(page, "393-dark-typing-load.png")

        # Room name (Other)
        await page.select_option("select[data-field='room']", "Other")
        await page.wait_for_selector("input[data-field='roomOther']")
        room_el = page.locator("input[data-field='roomOther']")
        await type_sentence(page, room_el, room, "Room name",
                            "() => document.activeElement && document.activeElement.getAttribute('data-field') === 'roomOther'")
        await shot(page, "393-dark-typing-room-other.png")

        # Light is in — custom (select may rerender once; typing must not)
        await page.select_option("#lightPlace", "Other")
        await page.wait_for_selector("input[data-field='lightRoomOther']")
        light_el = page.locator("input[data-field='lightRoomOther']")
        custom_light = "Bonus room at the back."
        await type_sentence(page, light_el, custom_light, "Light is in custom name",
                            "() => document.activeElement && document.activeElement.getAttribute('data-field') === 'lightRoomOther'")
        await shot(page, "393-dark-typing-light-place.png")

        # Note under More
        if await page.locator("textarea[data-field='note']").count() == 0 or not await page.locator("textarea[data-field='note']").is_visible():
            await page.click("#moreToggle")
            await page.wait_for_timeout(80)
        note_el = page.locator("textarea[data-field='note']")
        await note_el.wait_for(state="visible")
        await type_sentence(page, note_el, note, "Note",
                            "() => document.activeElement && document.activeElement.getAttribute('data-field') === 'note'")
        await shot(page, "393-dark-typing-note.png")

        # Custom fixture count
        await page.select_option("#loadType", "Can lights")
        await page.wait_for_timeout(80)
        if await page.locator("#fixtureOpen").count():
            await page.click("#fixtureOpen")
            await page.wait_for_timeout(80)
        await page.click('[data-field="fixtureCount"] .chip[data-value="8+"]')
        await page.wait_for_selector('input[data-field="fixtureCount"]')
        fix_el = page.locator('input[data-field="fixtureCount"]')
        await type_sentence(page, fix_el, fixtures, "Fixture count",
                            "() => document.activeElement && document.activeElement.getAttribute('data-field') === 'fixtureCount'")
        await shot(page, "393-dark-typing-fixture.png")

        # House name (on Summary)
        await page.click("[data-tab='summary']")
        await page.wait_for_selector("#homeName")
        home_el = page.locator("#homeName")
        await type_sentence(page, home_el, house, "House name",
                            "() => document.activeElement && document.activeElement.id === 'homeName'")
        await shot(page, "393-dark-typing-home-name.png")

        # New home name (on Homes)
        await page.click("[data-tab='homes']")
        await page.wait_for_selector("#newHomeName")
        new_el = page.locator("#newHomeName")
        await type_sentence(page, new_el, new_house, "New home name",
                            "() => document.activeElement && document.activeElement.id === 'newHomeName'")
        await shot(page, "393-dark-typing-new-home.png")

        # Light theme: note again (the reported field)
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(80)
        if await page.locator("textarea[data-field='note']").count() == 0 or not await page.locator("textarea[data-field='note']").is_visible():
            await page.click("#moreToggle")
            await page.wait_for_timeout(80)
        note_el = page.locator("textarea[data-field='note']")
        await note_el.wait_for(state="visible")
        # Note should still have the previous sentence from draft persist without render
        existing = await note_el.input_value()
        check("note value survived tab change", existing == note, repr(existing))
        extra = " Plus a second sentence in light mode."
        await note_el.click()
        # move to end and type more
        await note_el.press("End")
        await note_el.press_sequentially(extra, delay=30)
        focused = await page.evaluate("() => document.activeElement && document.activeElement.getAttribute('data-field') === 'note'")
        value = await note_el.input_value()
        check("light note keeps focus while adding a sentence", focused)
        check("light note keeps the combined value", value == note + extra, repr(value))
        await shot(page, "393-light-typing-note.png")

        await ctx.close()
        await browser.close()

    failed = [c for c in results["checks"] if not c["ok"]]
    print("\nSUMMARY", "PASS" if results["ok"] else f"FAIL {len(failed)}", "of", len(results["checks"]))
    for c in failed:
        print(" -", c["name"], ":", c["detail"][:300])
    sys.exit(0 if results["ok"] else 1)

asyncio.run(run())
