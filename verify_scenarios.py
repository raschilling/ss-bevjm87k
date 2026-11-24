"""End-to-end Switch Survey walks. Each scenario has a hand-computed expected order sheet."""
import asyncio, json, os, re, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = os.environ.get("SS_BASE", "http://127.0.0.1:8773/index.html")
OUT = Path(os.environ.get("SS_OUT", "/workspace/switch-survey/verify/scenarios"))
OUT.mkdir(parents=True, exist_ok=True)
PIN = os.environ.get("SS_TEST_PIN", "2468")
WEBKIT = "/home/box/.cache/ms-playwright/webkit-2388/pw_run.sh"
results = {"ok": True, "base": BASE, "scenarios": [], "checks": []}

def check(name, cond, detail=""):
    results["checks"].append({"name": name, "ok": bool(cond), "detail": str(detail)})
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not cond:
        results["ok"] = False
    return bool(cond)

def rec_scenario(name, ok, expected, actual, detail=""):
    results["scenarios"].append({"name": name, "ok": bool(ok), "expected": expected, "actual": actual, "detail": detail})
    check("scenario: " + name, ok, detail or json.dumps(actual, default=str))

async def press_pin(page, pin, confirm=False):
    await page.wait_for_selector("#keypad")
    for d in pin:
        await page.click(f'.key[data-key="{d}"]')
    await page.click('.key[data-key="OK"]')
    if confirm:
        await page.wait_for_timeout(80)
        for d in pin:
            await page.click(f'.key[data-key="{d}"]')
        await page.click('.key[data-key="OK"]')

async def shot(page, name):
    path = OUT / name
    await page.screenshot(path=str(path), full_page=True)
    return str(path)

def parse_qty(rows):
    return {r[0]: int(r[1]) for r in rows if len(r) >= 2 and str(r[1]).isdigit()}

async def qty_on(page):
    rows = await page.eval_on_selector_all("table tbody tr", "els => els.map(tr => [...tr.children].map(td => td.innerText.trim()))")
    return parse_qty(rows)

async def goto_walk_new_home(page, name):
    await page.click("[data-tab='homes']")
    await page.fill("#newHomeName", name)
    await page.click("text=Add home")
    await page.wait_for_timeout(150)
    await page.click("[data-tab='walk']")
    await page.wait_for_timeout(100)

async def set_floor(page, floor):
    if floor:
        await page.click(f'[data-field="floor"] .chip[data-value="{floor}"]')
        await page.wait_for_timeout(60)

async def pick_room_load(page, room, load, floor=None):
    if floor:
        await set_floor(page, floor)
    await page.select_option("select[data-field='room']", room)
    await page.select_option("select[data-field='load']", load)
    await page.wait_for_timeout(80)

async def open_more(page):
    more = page.locator("#more")
    if await more.count() and "hidden" in ((await more.get_attribute("class")) or "").split():
        await page.click("#moreToggle")
        await page.wait_for_timeout(80)

async def pick_existing_light(page, contains):
    await page.wait_for_selector("[data-pick-light]")
    chips = page.locator("[data-pick-light]")
    n = await chips.count()
    needle = contains.lower()
    labels = []
    for i in range(n):
        chip = chips.nth(i)
        label = ((await chip.get_attribute("data-label")) or (await chip.inner_text()) or "").strip()
        labels.append(label)
        if await chip.is_visible() and needle in label.lower():
            await chip.click()
            await page.wait_for_timeout(80)
            return label
    raise AssertionError(f"no visible light chip containing {contains!r}; chips={labels}")


async def set_fan(page, label):
    await page.click(f'[data-field="fanType"] .chip[data-value="{label}"]')
    await page.wait_for_timeout(60)

async def set_kind(page, label):
    await page.click(f'[data-field="kindOverride"] .chip[data-value="{label}"]')
    await page.wait_for_timeout(80)

UNSURE_DIMMABLE_NOTE = "Not sure if dimmable: set to on/off mode if the bulbs don't dim, or swap to dimmable LEDs."

async def open_hint(page, hint_id):
    btn = page.locator(f'[data-toggle-hint="{hint_id}"]')
    if await btn.count() and (await btn.get_attribute("aria-expanded")) != "true":
        await btn.click()
        await page.wait_for_timeout(60)

async def set_fixture(page, n):
    if await page.locator("#fixtureOpen").count():
        await page.click("#fixtureOpen")
        await page.wait_for_timeout(60)
    await page.wait_for_selector('[data-field="fixtureCount"]')
    if n > 8:
        await page.click('[data-field="fixtureCount"] .chip[data-value="8+"]')
        await page.wait_for_selector('input[data-field="fixtureCount"]')
        await page.fill('input[data-field="fixtureCount"]', str(n))
    else:
        await page.click(f'[data-field="fixtureCount"] .chip[data-value="{n}"]')
    await page.wait_for_timeout(80)

async def set_gang(page, size, pos=1):
    await open_more(page)
    await page.click(f'[data-field="gangSize"] .chip[data-value="{size}"]')
    await page.wait_for_timeout(80)
    if int(size) > 1:
        await page.click(f'[data-field="gangPosition"] .chip[data-value="{pos}"]')
        await page.wait_for_timeout(60)

async def save(page):
    await page.click("#saveSw")
    await page.wait_for_timeout(250)

async def log_dumb(page):
    await page.click("#logDumb")
    await page.wait_for_timeout(250)

async def has_same_or_new(page):
    return await page.locator("#sameOrNew").count() > 0

async def click_same_light(page, contains=None):
    await page.wait_for_selector("#sameOrNew")
    loc = page.locator("[data-same-light]")
    if contains:
        loc = page.locator("[data-same-light]").filter(has_text=re.compile(contains, re.I))
    await loc.first.click()
    await page.wait_for_timeout(250)

async def click_new_light(page, tag=None):
    await page.wait_for_selector("#newLight")
    await page.click("#newLight")
    await page.wait_for_timeout(150)
    if await page.locator("#newLightOk").count():
        if tag:
            await page.click(f'[data-field="pendingTag"] .chip[data-value="{tag}"]')
            await page.wait_for_timeout(60)
        await page.click("#newLightOk")
    await page.wait_for_timeout(250)

async def read_order(page):
    await page.click("[data-tab='summary']")
    await page.wait_for_timeout(200)
    q = await qty_on(page)
    body = await page.inner_text("body")
    dm = re.search(r"(\d+) regular \(not smart\)", body)
    loc = re.search(r"(\d+) location", body)
    verify = 0
    if "Verify on site" in body:
        # each verify item is a <p><strong>
        verify = await page.locator(".summary-side h2").evaluate_all(
            """els => {
              const i = els.findIndex(e => e.textContent.includes('Verify on site'));
              if (i < 0) return 0;
              const card = els[i].parentElement;
              return card.querySelectorAll('p > strong, p strong').length;
            }"""
        )
    actual = {
        "dimmer": q.get("Smart dimmer", 0),
        "onoff": q.get("Smart on/off", 0),
        "fan": q.get("Smart fan", 0),
        "companion": q.get("Companion", 0),
        "dumb": int(dm.group(1)) if dm else 0,
        "plates": {g: q.get(f"{g}-gang wallplate", 0) for g in (1, 2, 3, 4) if q.get(f"{g}-gang wallplate", 0)},
        "locations": int(loc.group(1)) if loc else 0,
        "verify": int(verify or 0),
        "wattage": "wattage" in body.lower(),
    }
    return actual, q, body

def order_equal(actual, expected):
    keys = ["dimmer", "onoff", "fan", "companion", "dumb", "locations", "verify"]
    for k in keys:
        if actual.get(k, 0) != expected.get(k, 0):
            return False, f"{k}: got {actual.get(k, 0)} expected {expected.get(k, 0)}"
    exp_p = {int(k): v for k, v in (expected.get("plates") or {}).items() if v}
    act_p = {int(k): v for k, v in (actual.get("plates") or {}).items() if v}
    if exp_p != act_p:
        return False, f"plates: got {act_p} expected {exp_p}"
    if "wattage" in expected and bool(actual.get("wattage")) != bool(expected.get("wattage")):
        return False, f"wattage: got {actual.get('wattage')} expected {expected.get('wattage')}"
    return True, ""

async def assert_order(page, name, expected):
    actual, q, body = await read_order(page)
    ok, why = order_equal(actual, expected)
    rec_scenario(name, ok, expected, actual, why)
    return ok, actual, body

async def parse_csv_shop(csv_text):
    lines = csv_text.splitlines()
    out = {}
    in_shop = False
    for line in lines:
        if line.strip() == "SHOPPING LIST":
            in_shop = True
            continue
        if in_shop:
            if not line.strip() or line.startswith("VERIFY") or line.startswith("BY FLOOR") or line.startswith("OPEN") or line.startswith("MULTI"):
                if line.startswith("Item"):
                    continue
                if not line.strip():
                    if out:
                        break
                    continue
                in_shop = False
                continue
            if line.startswith("Item"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                out[parts[0]] = int(parts[1])
    return out

async def run():
    async with async_playwright() as p:
        browser = await p.webkit.launch(executable_path=WEBKIT)
        ctx = await browser.new_context(viewport={"width": 393, "height": 852}, color_scheme="dark", device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(BASE, wait_until="load")
        await page.wait_for_selector("h1")
        check("title", await page.title() == "Switch Survey")
        await press_pin(page, PIN, confirm=True)
        await page.wait_for_selector("[data-tab='walk']")
        body = await page.inner_text("body")
        check("Survey tab label", (await page.locator('[data-tab="walk"]').inner_text()).strip() == "Survey")
        check("no yes/no light question on main survey", "Is the light in this room?" not in body and "Light is in a different room" not in body and "Where is the light?" not in body)
        await open_hint(page, "addSwitch")
        body = await page.inner_text("body")
        check("intro is Survey every switch in order", "Survey every switch in order" in body)
        check("intro mentions tap a logged light name", "tap its name in the list of lights already logged" in body)
        check("Which one? is not on the form", "Which one?" not in body and await page.locator('[data-field="qualifier"]').count() == 0)
        check("Switch type has Not sure if dimmable", "Not sure if dimmable" in body)
        check("fixture count is not on the main form", await page.locator("#fixtureOpen").count() == 0 and "Fixtures on this switch" not in body)

        # Exterior floor switches the room list to outdoor spots
        await page.click('[data-field="floor"] .chip[data-value="Exterior"]')
        await page.wait_for_timeout(80)
        opts = await page.locator("select[data-field='room'] option").all_text_contents()
        check("Exterior rooms are outdoor spots",
              "Front porch" in opts and "Driveway" in opts and "Back patio" in opts and "Deck" in opts
              and "Garage exterior" in opts and "Landscape" in opts and "Side door" in opts and "Other" in opts
              and "Kitchen" not in opts and "Hall" not in opts and "Basement" not in opts and opts.count("Exterior") == 0,
              opts)
        await shot(page, "393-dark-exterior-rooms.png")
        await page.click('[data-field="floor"] .chip[data-value="Main"]')
        await page.wait_for_timeout(80)
        # Close the intro hint and wait out the PIN flash so the measure is a typical entry.
        btn = page.locator('[data-toggle-hint="addSwitch"]')
        if await btn.count() and (await btn.get_attribute("aria-expanded")) == "true":
            await btn.click()
            await page.wait_for_timeout(60)
        flash = page.locator(".banner")
        if await flash.count():
            await flash.wait_for(state="hidden", timeout=6000)
        await pick_room_load(page, "Kitchen", "Can lights")
        metrics = await page.evaluate("""() => {
          const save = document.getElementById('saveSw');
          const r = save ? save.getBoundingClientRect() : null;
          return {
            scrollHeight: document.documentElement.scrollHeight,
            clientHeight: document.documentElement.clientHeight,
            innerHeight: window.innerHeight,
            saveBottom: r ? r.bottom : null,
            saveTop: r ? r.top : null
          };
        }""")
        overflow = max(0, int(metrics["scrollHeight"]) - int(metrics["clientHeight"]))
        save_in_view = metrics["saveBottom"] is not None and metrics["saveBottom"] <= metrics["innerHeight"] + 1
        check("393x852 form: Save is in view without scrolling", save_in_view,
              f"saveBottom={metrics['saveBottom']} innerHeight={metrics['innerHeight']} overflow={overflow}px {metrics}")
        results["formFit"] = {**metrics, "overflowPx": overflow, "saveInView": save_in_view}
        print("FORM FIT 393x852", results["formFit"])
        await shot(page, "393-dark-survey-form.png")

        # 1. Simple room + 3-gang box
        await goto_walk_new_home(page, "S1 Simple and 3-gang")
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        check("S1 first cans no Same/New prompt", not await has_same_or_new(page))
        await pick_room_load(page, "Kitchen", "Lamp outlet")
        await save(page)
        await pick_room_load(page, "Living room", "Can lights")
        await set_gang(page, 3, 1)
        await save(page)
        await pick_room_load(page, "Living room", "Sconces")
        await set_gang(page, 3, 2)
        await save(page)
        await pick_room_load(page, "Living room", "Lamp outlet")
        await set_gang(page, 3, 3)
        await save(page)
        # Kitchen 1 dimmer + 1 onoff (1-gang x2). Living 2 dimmer + 1 onoff in one 3-gang.
        await assert_order(page, "S1 simple room + 3-gang box", {
            "dimmer": 3, "onoff": 2, "fan": 0, "companion": 0, "dumb": 0,
            "plates": {1: 2, 3: 1}, "locations": 5, "verify": 0
        })

        # 2. Stairs 3-way across floors via light-name chip
        await goto_walk_new_home(page, "S2 Stairs 3-way")
        await pick_room_load(page, "Hall", "Can lights", floor="Upper")
        await save(page)
        await pick_room_load(page, "Stairs", "Can lights", floor="Main")
        check("S2 shows Upper Hall cans chip", "Upper Hall cans" in (await page.inner_text("body")))
        await pick_existing_light(page, "Upper Hall cans")
        await save(page)
        check("S2 auto-linked via chip, no Same/New", not await has_same_or_new(page))
        body = await page.inner_text("body")
        check("S2 3-way badge or flash", "3-way" in body or "Linked as a 3-way" in body)
        await assert_order(page, "S2 stairs 3-way across floors", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 1, "dumb": 0,
            "plates": {1: 2}, "locations": 2, "verify": 0
        })

        # 3. Same-room 3-way via Same light
        await goto_walk_new_home(page, "S3 Same-room 3-way")
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        check("S3 prompts Same light vs New light", await has_same_or_new(page) and "New light" in (await page.inner_text("body")) and "Same light as" in (await page.inner_text("body")))
        await click_same_light(page, "Kitchen")
        await assert_order(page, "S3 same-room 3-way", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 1, "dumb": 0,
            "plates": {1: 2}, "locations": 2, "verify": 0
        })

        # 4. 4-way hall
        await goto_walk_new_home(page, "S4 4-way hall")
        await pick_room_load(page, "Hall", "Can lights")
        await save(page)
        await pick_room_load(page, "Foyer", "Can lights")
        check("S4 shows Main Hall cans chip", "Main Hall cans" in (await page.inner_text("body")))
        await pick_existing_light(page, "Main Hall cans")
        await save(page)
        await pick_room_load(page, "Living room", "Can lights")
        await pick_existing_light(page, "Main Hall cans")
        await save(page)
        await assert_order(page, "S4 4-way hall", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 2, "dumb": 0,
            "plates": {1: 3}, "locations": 3, "verify": 0
        })
        check("S4 4-way badge", "4-way (3 locations)" in (await page.inner_text("body")))

        # 5. Kitchen 3 can groups: first cans (3-way), sink (3-way), #2 (single).
        # Tags come only from the Same light / New light prompt, not a form field.
        await goto_walk_new_home(page, "S5 Kitchen three can groups")
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        check("S5 first cans, no prompt", not await has_same_or_new(page))
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        check("S5 second cans asks Same/New (no silent merge)", await has_same_or_new(page))
        await click_same_light(page, "cans")
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        check("S5 first sink asks Same/New", await has_same_or_new(page))
        await click_new_light(page, "Sink")
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        check("S5 second sink asks Same/New", await has_same_or_new(page))
        await click_same_light(page, "sink")
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        check("S5 third group asks Same/New", await has_same_or_new(page))
        body = await page.inner_text("body")
        check("S5 prompt names show tags", "sink" in body.lower())
        await click_new_light(page, "#2")
        body = await page.inner_text("body")
        check("S5 walk list shows cans, sink, #2", "sink" in body.lower() and "#2" in body)
        await assert_order(page, "S5 kitchen cans/sink/#2 with 3-ways", {
            "dimmer": 3, "onoff": 0, "fan": 0, "companion": 2, "dumb": 0,
            "plates": {1: 5}, "locations": 5, "verify": 0
        })
        await shot(page, "393-dark-summary.png")
        await page.click("[data-tab='walk']")
        await pick_room_load(page, "Kitchen", "Can lights")
        body = await page.inner_text("body")
        check("S5 walk form shows tagged light chips", "sink cans" in body.lower() and "#2 cans" in body.lower())
        check("filter box on walk form", await page.locator('input[data-field="lightFilter"]').count() > 0)
        await shot(page, "393-dark-walk-form.png")

        # 6. Kitchen cans vs Hall cans must not merge
        await goto_walk_new_home(page, "S6 Kitchen vs Hall")
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        await pick_room_load(page, "Hall", "Can lights")
        await save(page)
        check("S6 no Same/New prompt", not await has_same_or_new(page))
        await assert_order(page, "S6 Kitchen cans vs Hall cans", {
            "dimmer": 2, "onoff": 0, "fan": 0, "companion": 0, "dumb": 0,
            "plates": {1: 2}, "locations": 2, "verify": 0
        })

        # 7. AC, DC, Not sure fans
        await goto_walk_new_home(page, "S7 Fans AC DC Not sure")
        await pick_room_load(page, "Bedroom", "Ceiling fan")
        await set_fan(page, "AC")
        await save(page)
        await pick_room_load(page, "Office", "Ceiling fan")
        await set_fan(page, "DC")
        await save(page)
        await pick_room_load(page, "Primary bedroom", "Ceiling fan")
        await set_fan(page, "Not sure")
        await save(page)
        ok, actual, body = await assert_order(page, "S7 AC / DC / Not sure fans", {
            "dimmer": 0, "onoff": 1, "fan": 1, "companion": 0, "dumb": 0,
            "plates": {1: 3}, "locations": 3, "verify": 1
        })
        check("S7 DC constant-power note", "DC" in body and "constant power" in body.lower())
        check("S7 verify-on-site names the unsure fan", "Verify on site" in body and "Primary bedroom" in body)

        # 8. Regular switch + optional fixture count 6 and 8+
        await goto_walk_new_home(page, "S8 Regular and fixture counts")
        await pick_room_load(page, "Closet", "Closet light")
        await log_dumb(page)
        await pick_room_load(page, "Hall", "Can lights")
        check("S8 fixture count starts collapsed", await page.locator("#fixtureOpen").count() > 0)
        await set_fixture(page, 6)
        await save(page)
        await pick_room_load(page, "Living room", "Can lights")
        await set_fixture(page, 10)
        await save(page)
        ok, actual, body = await assert_order(page, "S8 regular + fixture count 6 and 8+", {
            "dimmer": 2, "onoff": 0, "fan": 0, "companion": 0, "dumb": 1,
            "plates": {1: 2}, "locations": 3, "verify": 0, "wattage": True
        })
        check("S8 walk/summary mentions x6 and x10 or wattage", "x6" in body or "Hall cans x6" in body or "wattage" in body.lower())

        # 9. Single-pole later 3-way; delete changes groups
        await goto_walk_new_home(page, "S9 Relog and delete")
        await pick_room_load(page, "Dining room", "Can lights")
        await save(page)
        await assert_order(page, "S9 single-pole before second end", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 0, "dumb": 0,
            "plates": {1: 1}, "locations": 1, "verify": 0
        })
        await page.click("[data-tab='walk']")
        await pick_room_load(page, "Dining room", "Can lights")
        await save(page)
        check("S9 second end prompts (duplicate handling)", await has_same_or_new(page))
        await click_same_light(page)
        await assert_order(page, "S9 later relogged as 3-way", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 1, "dumb": 0,
            "plates": {1: 2}, "locations": 2, "verify": 0
        })
        # Delete one member — group should collapse
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(100)
        if await page.locator("[data-edit]").count():
            await page.locator("[data-edit]").first.click()
            await page.wait_for_timeout(150)
            page.once("dialog", lambda d: asyncio.create_task(d.accept()))
            if await page.locator("#deleteSw").count():
                await page.click("#deleteSw")
                await page.wait_for_timeout(300)
        await assert_order(page, "S9 delete mid-walk changes the group", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 0, "dumb": 0,
            "plates": {1: 1}, "locations": 1, "verify": 0
        })

        # 10. Unlink and merge on Summary
        await goto_walk_new_home(page, "S10 Unlink and merge")
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        await click_same_light(page)
        ok, _, _ = await assert_order(page, "S10 grouped before unlink", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 1, "dumb": 0,
            "plates": {1: 2}, "locations": 2, "verify": 0
        })
        if await page.locator("[data-unlink]").count():
            await page.locator("[data-unlink]").first.click()
            await page.wait_for_timeout(250)
        await assert_order(page, "S10 after unlink", {
            "dimmer": 2, "onoff": 0, "fan": 0, "companion": 0, "dumb": 0,
            "plates": {1: 2}, "locations": 2, "verify": 0
        })
        if await page.locator("select[data-merge-from]").count():
            sel = page.locator("select[data-merge-from]").first
            options = await sel.locator("option").all()
            val = ""
            for opt in options:
                v = await opt.get_attribute("value")
                if v:
                    val = v
                    break
            if val:
                await sel.select_option(val)
                await page.wait_for_timeout(250)
        await assert_order(page, "S10 after merge", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 1, "dumb": 0,
            "plates": {1: 2}, "locations": 2, "verify": 0
        })

        # 11. Reload + PIN mid-walk, nothing lost
        await goto_walk_new_home(page, "S11 Persistence")
        await pick_room_load(page, "Office", "Pendants")
        await set_fixture(page, 3)
        await save(page)
        await pick_room_load(page, "Office", "Sconces")
        await save(page)
        await page.reload(wait_until="load")
        await page.wait_for_selector("#keypad")
        title = await page.inner_text(".card h2")
        check("S11 reload is Enter PIN once", "Enter PIN" in title and "Set a PIN" not in title)
        await press_pin(page, PIN, confirm=False)
        await page.wait_for_selector("[data-tab='walk']", timeout=4000)
        await page.click("[data-tab='homes']")
        await page.wait_for_timeout(100)
        check("S11 home still listed", "S11 Persistence" in (await page.inner_text("body")))
        # select the home
        if await page.locator("text=S11 Persistence").count():
            await page.click("text=S11 Persistence")
            await page.wait_for_timeout(150)
        await assert_order(page, "S11 reload kept both Office lights", {
            "dimmer": 2, "onoff": 0, "fan": 0, "companion": 0, "dumb": 0,
            "plates": {1: 2}, "locations": 2, "verify": 0
        })

        # 12. Multiple homes kept separate + CSV/JSON match Summary
        await goto_walk_new_home(page, "S12 Home A")
        await pick_room_load(page, "Kitchen", "Can lights")
        await save(page)
        await assert_order(page, "S12 Home A only 1 dimmer", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 0, "dumb": 0,
            "plates": {1: 1}, "locations": 1, "verify": 0
        })
        await goto_walk_new_home(page, "S12 Home B")
        await pick_room_load(page, "Hall", "Can lights")
        await save(page)
        await pick_room_load(page, "Hall", "Can lights")
        await save(page)
        await click_same_light(page)
        await pick_room_load(page, "Bedroom", "Ceiling fan")
        await set_fan(page, "AC")
        await save(page)
        ok, actual_b, _ = await assert_order(page, "S12 Home B 1 dimmer + 1 companion + 1 fan", {
            "dimmer": 1, "onoff": 0, "fan": 1, "companion": 1, "dumb": 0,
            "plates": {1: 3}, "locations": 3, "verify": 0
        })
        async with page.expect_download() as dl:
            await page.click("#exportCsv")
        csvp = OUT / "s12-home-b.csv"
        await (await dl.value).save_as(str(csvp))
        shop = await parse_csv_shop(csvp.read_text(encoding="utf-8"))
        check("S12 CSV shopping list matches Summary",
              shop.get("Smart dimmer") == 1 and shop.get("Companion") == 1 and shop.get("Smart fan") == 1
              and shop.get("1-gang wallplate") == 3,
              shop)
        async with page.expect_download() as dl:
            await page.click("#exportJson")
        jp = OUT / "s12-home-b.json"
        await (await dl.value).save_as(str(jp))
        data = json.loads(jp.read_text(encoding="utf-8"))
        homes = data.get("homes") or []
        check("S12 JSON is a Switch Survey backup", data.get("kind") == "ha-switch-survey" and homes)
        b = next((h for h in homes if h.get("name") == "S12 Home B"), homes[0] if homes else {})
        check("S12 JSON Home B has 3 switches", len(b.get("switches") or []) == 3, len((b or {}).get("switches") or []))
        # switch back to A
        await page.click("[data-tab='homes']")
        await page.wait_for_timeout(100)
        await page.click("text=S12 Home A")
        await page.wait_for_timeout(150)
        await assert_order(page, "S12 Home A unchanged after working in B", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 0, "dumb": 0,
            "plates": {1: 1}, "locations": 1, "verify": 0
        })


        # 13. Not sure if dimmable still orders dimmers
        await goto_walk_new_home(page, "S13 Not sure dimmable")
        await pick_room_load(page, "Living room", "Can lights")
        check("S13 form offers Not sure if dimmable", "Not sure if dimmable" in (await page.inner_text("body")))
        await save(page)
        await pick_room_load(page, "Kitchen", "Can lights")
        await set_kind(page, "Not sure if dimmable")
        body = await page.inner_text("body")
        check("S13 preview orders as a Dimmer", "orders as a Dimmer (not sure if dimmable)" in body)
        await shot(page, "393-dark-walk-unsure.png")
        await save(page)
        await pick_room_load(page, "Hall", "Can lights")
        await set_kind(page, "Not sure if dimmable")
        await save(page)
        await pick_room_load(page, "Office", "Can lights")
        await set_kind(page, "Not sure if dimmable")
        await save(page)
        await pick_room_load(page, "Closet", "Closet light")
        await save(page)
        ok, actual, body = await assert_order(page, "S13 not-sure-dimmable orders dimmers", {
            "dimmer": 4, "onoff": 1, "fan": 0, "companion": 0, "dumb": 0,
            "plates": {1: 5}, "locations": 5, "verify": 0
        })
        check("S13 summary count", "3 dimmers marked not-sure-dimmable" in body)
        check("S13 exact note on order sheet", UNSURE_DIMMABLE_NOTE in body)
        check("S13 undecided brand note", "Inovelli Blue and Red dimmers have an on/off mode" in body and "Caseta in-wall dimmers do not" in body and "full brightness" in body)
        await page.click('[data-field="brand"] .chip[data-value="Inovelli"]')
        await page.wait_for_timeout(80)
        body = await page.inner_text("body")
        check("S13 Inovelli brand note", "Inovelli Blue and Red dimmers have an on/off mode" in body and "set the dimmer to on/off" in body)
        check("S13 Inovelli note is not the Caseta in-wall wording", "no on/off mode on the dimmer itself" not in body)
        await page.click('[data-field="brand"] .chip[data-value="Lutron Caseta"]')
        await page.wait_for_timeout(80)
        body = await page.inner_text("body")
        check("S13 Caseta brand note", "no on/off mode on the dimmer itself" in body and "full brightness" in body and "Lutron rates the in-wall dimmer for dimmable lamps only" in body)
        check("S13 exact note still present under Caseta", UNSURE_DIMMABLE_NOTE in body)
        await shot(page, "393-dark-summary-unsure.png")
        async with page.expect_download() as dl:
            await page.click("#exportCsv")
        csvp = OUT / "s13-not-sure-dimmable.csv"
        await (await dl.value).save_as(str(csvp))
        csv = csvp.read_text(encoding="utf-8")
        shop = await parse_csv_shop(csv)
        check("S13 CSV shopping list is 4 dimmers + 1 on/off + 5 plates",
              shop.get("Smart dimmer") == 4 and shop.get("Smart on/off") == 1 and shop.get("1-gang wallplate") == 5, shop)
        check("S13 CSV has exact note", UNSURE_DIMMABLE_NOTE in csv)
        check("S13 CSV has count line", "3 dimmers marked not-sure-dimmable" in csv)
        async with page.expect_download() as dl:
            await page.click("#exportJson")
        jp = OUT / "s13-not-sure-dimmable.json"
        await (await dl.value).save_as(str(jp))
        data = json.loads(jp.read_text(encoding="utf-8"))
        homes = data.get("homes") or []
        h = next((x for x in homes if x.get("name") == "S13 Not sure dimmable"), homes[0] if homes else {})
        switches = h.get("switches") or []
        unsure = [s for s in switches if s.get("kindOverride") == "unsure-dimmable"]
        check("S13 JSON has 5 switches, 3 marked unsure-dimmable", len(switches) == 5 and len(unsure) == 3, (len(switches), len(unsure)))
        notes = h.get("shoppingNotes") or data.get("shoppingNotes") or []
        check("S13 JSON shoppingNotes include the exact note", UNSURE_DIMMABLE_NOTE in notes, notes)

        # Light theme screenshots of walk form + summary, chips visible
        await page.click("[data-tab='homes']")
        await page.wait_for_timeout(80)
        await page.click("text=S5 Kitchen three can groups")
        await page.wait_for_timeout(150)
        await page.emulate_media(color_scheme="light")
        await page.set_viewport_size({"width": 393, "height": 852})
        await page.click("[data-tab='walk']")
        await pick_room_load(page, "Kitchen", "Can lights")
        bg = await page.eval_on_selector("body", "el => getComputedStyle(el).backgroundColor")
        check("light bg", bg.replace(" ", "") == "rgb(243,241,234)", bg)
        body = await page.inner_text("body")
        check("light walk form shows tagged light chips", "sink cans" in body.lower() and "#2 cans" in body.lower())
        await shot(page, "393-light-walk-form.png")
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-summary.png")

        await page.click("[data-tab='homes']")
        await page.wait_for_timeout(80)
        await page.click("text=S13 Not sure dimmable")
        await page.wait_for_timeout(150)
        await page.click("[data-tab='walk']")
        await pick_room_load(page, "Kitchen", "Can lights")
        await set_kind(page, "Not sure if dimmable")
        body = await page.inner_text("body")
        check("light walk form shows Not sure if dimmable", "Not sure if dimmable" in body)
        await shot(page, "393-light-walk-unsure.png")
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(80)
        body = await page.inner_text("body")
        check("light summary shows not-sure count and note", "3 dimmers marked not-sure-dimmable" in body and UNSURE_DIMMABLE_NOTE in body)
        await shot(page, "393-light-summary-unsure.png")

        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)
        await page.click('[data-field="floor"] .chip[data-value="Exterior"]')
        await page.wait_for_timeout(80)
        opts = await page.locator("select[data-field='room'] option").all_text_contents()
        check("light Exterior rooms are outdoor spots", "Front porch" in opts and "Kitchen" not in opts, opts)
        await shot(page, "393-light-exterior-rooms.png")

        # clear
        await page.reload(wait_until="load")
        await page.wait_for_selector("#forgot")
        await page.click("#forgot")
        await page.click("#forgotWarn")
        await page.click("#forgotConfirm")
        await page.wait_for_timeout(150)
        has = await page.evaluate("() => localStorage.getItem('switchSurvey.meta.v1')")
        check("storage cleared", has is None, has)
        await ctx.close()
        await browser.close()

    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    print("\n==== SCENARIO TABLE ====")
    for s in results["scenarios"]:
        print(("PASS" if s["ok"] else "FAIL"), s["name"], "" if s["ok"] else ("— " + s["detail"] + " expected " + json.dumps(s["expected"]) + " got " + json.dumps(s["actual"])))
    failed_s = [s for s in results["scenarios"] if not s["ok"]]
    failed_c = [c for c in results["checks"] if not c["ok"]]
    print("\nSUMMARY", "PASS" if results["ok"] else "FAIL", f"{len(results['scenarios'])-len(failed_s)}/{len(results['scenarios'])} scenarios,", f"{len(results['checks'])-len(failed_c)}/{len(results['checks'])} checks")
    for c in failed_c:
        if not c["name"].startswith("scenario:"):
            print(" -", c["name"], ":", str(c["detail"])[:300])
    sys.exit(0 if results["ok"] else 1)

asyncio.run(run())
