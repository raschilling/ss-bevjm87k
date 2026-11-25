"""End-to-end Switch Survey walks. Each scenario has a hand-computed expected order sheet."""
import asyncio, json, os, re, sys
from pathlib import Path
from playwright.async_api import async_playwright
from verify_helpers import choose_load, pick_existing_light, open_more, set_other_spots, show_parts, set_light_place

BASE = os.environ.get("SS_BASE", "http://127.0.0.1:8773/index.html")
OUT = Path(os.environ.get("SS_OUT", "/workspace/switch-survey/verify/scenarios"))
OUT.mkdir(parents=True, exist_ok=True)
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

async def shot(page, name):
    path = OUT / name
    await page.screenshot(path=str(path), full_page=True)
    return str(path)

def parse_qty(rows):
    return {r[0]: int(r[1]) for r in rows if len(r) >= 2 and str(r[1]).isdigit()}

async def qty_on(page):
    await show_parts(page)
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
    await choose_load(page, load)
    await page.wait_for_timeout(80)

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
    dm = re.search(r"(\d+) Keep as is \(not smart\)", body)
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
        "plates": {g: q.get(f"{g}-gang wallplate", 0) for g in (1, 2, 3, 4, 5, 6) if q.get(f"{g}-gang wallplate", 0)},
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
        await page.wait_for_selector("[data-tab='walk']")
        body = await page.inner_text("body")
        check("first launch has no PIN screen",
              await page.locator("#keypad").count() == 0 and "Set a PIN" not in body and "Enter PIN" not in body
              and "Change PIN" not in body and "Open your saved survey" not in body)
        check("first launch is the survey form", "Add a switch" in body and "Save switch" in body)
        check("Keep as is (not smart) is on the form", "Keep as is (not smart)" in body and "Regular switch" not in body)
        check("gang is on the first-launch form", "Switches in this box" in body)
        check("gang options include 5 and 6",
              await page.locator('[data-field="gangSize"] .chip[data-value="5"]').count() > 0
              and await page.locator('[data-field="gangSize"] .chip[data-value="6"]').count() > 0)
        load_opts = await page.locator("#loadType option").all_text_contents()
        check("What it controls is an A-Z type dropdown", await page.locator("#loadType").count() > 0 and await page.locator("#loadSuggest").count() == 0, load_opts)
        check("Unknown / find out is at the top of the type list",
              any("Unknown / find out" in (o or "") for o in load_opts)
              and [o.strip() for o in load_opts if o.strip() and "Type or choose" not in o][0] == "Unknown / find out",
              load_opts)
        check("Accent lights is in the type list", "Accent lights" in load_opts)
        check("Ring camera is in the type list", "Ring camera" in load_opts)
        check("Upper cabinet lights is in the type list", "Upper cabinet lights" in load_opts)
        check("Under-cabinet is still in the type list", "Under-cabinet" in load_opts)
        check("Light is in is on the first-launch form", await page.locator("#lightPlace").count() > 0 and "Light is in" in body)
        same_opt = await page.locator("#lightPlace option[value='same']").text_content()
        check("Light is in defaults to same as the switch", (same_opt or "").strip().lower().startswith("same as") or "same as switch" in (same_opt or "").lower(), same_opt)
        check("Also controlled from is gone", "Also controlled from" not in body and "Doorway or wall" not in body and "Lights already logged" not in body)
        save_box = await page.locator("#saveSw").bounding_box()
        check("Save fits on 393x852 with gang visible", bool(save_box) and save_box["y"] + save_box["height"] <= 852, save_box)
        await shot(page, "393-dark-first-launch.png")
        check("Survey tab label", (await page.locator('[data-tab="walk"]').inner_text()).strip() == "Survey")
        check("no yes/no light question on main survey", "Is the light in this room?" not in body and "Light is in a different room" not in body and "Where is the light?" not in body)
        await open_hint(page, "addSwitch")
        body = await page.inner_text("body")
        check("intro is Survey every switch in order", "Survey every switch in order" in body)
        check("intro mentions typing a logged light", "start typing under What it controls" in body or "What it controls" in body)
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
        # Close the intro hint so the measure is a typical entry.
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
        await page.locator("#loadQuery").click()
        await page.wait_for_timeout(80)
        check("S2 shows Upper Hall suggestion", "Same light as Can lights (in Upper Hall)" in (await page.inner_text("body")))
        await page.locator("h1").click()
        await page.wait_for_timeout(80)
        await pick_existing_light(page, "Upper Hall")
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
        same_in_load = await page.locator("#loadWrap #sameOrNew").count()
        check("S3 Same/New prompt is inline under What it controls", same_in_load == 1)
        prompt_box = await page.locator("#sameOrNew").bounding_box()
        check("S3 Same/New prompt is in the 393 viewport", bool(prompt_box) and prompt_box["y"] >= 0 and prompt_box["y"] < 852, prompt_box)
        y_before = await page.evaluate("() => window.scrollY")
        await save(page)
        y_after = await page.evaluate("() => window.scrollY")
        check("S3 ignoring the prompt blocks save", await has_same_or_new(page))
        check("S3 save-blocked does not jump to the top", y_after <= y_before + 20 or await page.locator("#sameOrNew").bounding_box() is not None, {"before": y_before, "after": y_after})
        await page.set_viewport_size({"width": 393, "height": 500})
        await page.wait_for_timeout(400)
        pb = await page.locator("#sameOrNew").bounding_box()
        check("S3 prompt stays in a short keyboard viewport", bool(pb) and pb["y"] >= 0 and pb["y"] + min(pb["height"], 80) <= 500, pb)
        await page.set_viewport_size({"width": 393, "height": 852})
        await page.wait_for_timeout(80)
        await shot(page, "393-dark-same-new-prompt.png")
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
        await page.locator("#loadQuery").click()
        await page.wait_for_timeout(80)
        check("S4 shows Hall suggestion", "Same light as Can lights (in Hall)" in (await page.inner_text("body")))
        await page.locator("h1").click()
        await page.wait_for_timeout(80)
        await pick_existing_light(page, "Same light as Can lights (in Hall")
        await save(page)
        await pick_room_load(page, "Living room", "Can lights")
        await pick_existing_light(page, "Same light as Can lights (in Hall")
        await save(page)
        await assert_order(page, "S4 4-way hall", {
            "dimmer": 1, "onoff": 0, "fan": 0, "companion": 2, "dumb": 0,
            "plates": {1: 3}, "locations": 3, "verify": 0
        })
        check("S4 4-way summary badge", "4-way (3 locations)" in (await page.inner_text("body")))
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(100)
        body = await page.inner_text("body")
        check("S4 walk position badges", "4-way 1/3" in body and "4-way 2/3" in body and "4-way 3/3" in body)
        check("S4 walk has no N locations badge", "4-way (3 locations)" not in body)

        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(150)
        body = await page.inner_text("body")
        check("S4 install list is the default summary", "Install list" in body and "Print / Save PDF" in body and ("Show parts to order" in body or "Hide parts to order" in body))
        check("S4 install list has 4-way other ends", "4-way 1/3" in body and "other end" in body.lower() and "-gang box" in body)
        await shot(page, "393-dark-install-list.png")
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-install-list.png")
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(80)
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)

        # After Save, the form resets for the next switch. Picking a type
        # from the dropdown (not filling the field) should immediately show Same light as…
        await goto_walk_new_home(page, "Save reset and chip suggest")
        await pick_room_load(page, "Kitchen", "Can lights")
        await set_gang(page, 3, 1)
        await save(page)
        load_val = await page.locator("#loadQuery").input_value()
        check("after save, load field is cleared", (load_val or "").strip() == "")
        check("after save, room is kept", await page.locator("select[data-field='room']").input_value() == "Kitchen")
        check("after save, slot advances in a 3-gang box",
              await page.locator('[data-field="gangSize"] .chip[data-value="3"][aria-pressed="true"]').count() > 0
              and await page.locator('[data-field="gangPosition"] .chip[data-value="2"][aria-pressed="true"]').count() > 0)
        check("Clear for next is still a manual reset", await page.locator("#clearDraft").count() > 0)
        check("type dropdown is visible after save without focusing",
              await page.locator("#loadType").count() > 0
              and await page.locator("#loadType option[value='Can lights']").count() > 0)
        await page.select_option("#loadType", "Can lights")
        await page.wait_for_timeout(150)
        same = page.locator("#sameLightSuggest [data-pick-light]")
        check("picking a type from the dropdown shows Same light as chips", await same.count() > 0 and await same.first.is_visible())
        body = await page.inner_text("#sameLightSuggest")
        check("same-light chip names the room", "Same light as Can lights (in Kitchen)" in body)
        await shot(page, "393-dark-same-light-after-chip.png")
        await page.click("#clearDraft")
        await page.wait_for_timeout(80)
        await page.locator("#loadQuery").click()
        await page.locator("#loadQuery").fill("can")
        await page.wait_for_timeout(150)
        check("typing a load type shows Same light as chips",
              "Same light as Can lights (in Kitchen)" in (await page.inner_text("#sameLightSuggest")))
        await shot(page, "393-dark-same-light-after-type.png")
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-same-light-after-type.png")
        await page.click("#clearDraft")
        await page.wait_for_timeout(80)
        await page.select_option("#loadType", "Can lights")
        await page.wait_for_timeout(150)
        check("light: picking a type from the dropdown shows Same light as chips",
              await page.locator("#sameLightSuggest [data-pick-light]").count() > 0)
        await shot(page, "393-light-same-light-after-chip.png")
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(80)

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
        check("S5 walk form shows tagged light chips", "same light as sink" in body.lower() and "same light as #2" in body.lower())
        check("What it controls is a single input", await page.locator("#loadQuery").count() > 0 and await page.locator('input[data-field="lightFilter"]').count() == 0 and "Lights already logged" not in (await page.inner_text("body")))
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
        await pick_room_load(page, "Guest bath", "Exhaust fan")
        body = await page.inner_text("body")
        check("S7 exhaust has no fan type question", "Fan type" not in body)
        check("S7 exhaust preview is on/off", "On/off" in body or "on/off" in body.lower())
        await save(page)
        ok, actual, body = await assert_order(page, "S7 AC / DC / Not sure fans plus exhaust", {
            "dimmer": 0, "onoff": 2, "fan": 1, "companion": 0, "dumb": 0,
            "plates": {1: 4}, "locations": 4, "verify": 1
        })
        check("S7 DC constant-power note", "DC" in body and "constant power" in body.lower())
        check("S7 verify-on-site names the unsure fan", "Verify on site" in body and "Primary bedroom" in body)
        check("S7 exhaust is an on/off, not a fan switch", (actual or {}).get("onoff") == 2 and (actual or {}).get("fan") == 1, actual)

        # 8. Keep as is (not smart) + optional fixture count 6 and 8+
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
        ok, actual, body = await assert_order(page, "S8 keep as is + fixture count 6 and 8+", {
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

        # 11. Reload mid-survey, nothing lost (no PIN)
        await goto_walk_new_home(page, "S11 Persistence")
        await pick_room_load(page, "Office", "Pendants")
        await set_fixture(page, 3)
        await save(page)
        await pick_room_load(page, "Office", "Sconces")
        await save(page)
        await page.reload(wait_until="load")
        await page.wait_for_selector("[data-tab='walk']", timeout=4000)
        body = await page.inner_text("body")
        check("S11 reload has no PIN screen",
              await page.locator("#keypad").count() == 0 and "Enter PIN" not in body and "Set a PIN" not in body)
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
            await show_parts(page)
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
            await show_parts(page)
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


        # 14. 6-gang box: slots 1–6, auto-advance, install list, parts
        await goto_walk_new_home(page, "S14 6-gang box")
        await page.set_viewport_size({"width": 393, "height": 852})
        check("S14 form offers 5-gang and 6-gang",
              await page.locator('[data-field="gangSize"] .chip[data-value="5"]').count() > 0
              and await page.locator('[data-field="gangSize"] .chip[data-value="6"]').count() > 0)
        await page.click('[data-field="gangSize"] .chip[data-value="5"]')
        await page.wait_for_timeout(80)
        check("S14 5-gang shows slots 1-5",
              await page.locator('[data-field="gangPosition"] .chip[data-value="5"]').count() > 0
              and await page.locator('[data-field="gangPosition"] .chip[data-value="6"]').count() == 0)
        await pick_room_load(page, "Kitchen", "Can lights")
        await set_gang(page, 6, 1)
        check("S14 6-gang shows slots 1-6",
              await page.locator('[data-field="gangPosition"] .chip[data-value="6"]').count() > 0
              and await page.locator('[data-field="gangPosition"] .chip[data-value="7"]').count() == 0)
        # Chip fit at 393: no horizontal overflow, all six size chips visible
        ov = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        check("S14 393 gang chips do not overflow the screen", ov)
        await shot(page, "393-dark-6-gang-form.png")
        await save(page)
        check("S14 after slot 1, advances to slot 2",
              await page.locator('[data-field="gangSize"] .chip[data-value="6"][aria-pressed="true"]').count() > 0
              and await page.locator('[data-field="gangPosition"] .chip[data-value="2"][aria-pressed="true"]').count() > 0)
        six_loads = ["Pendants", "Under-cabinet", "Lamp outlet", "Exhaust fan", "Sconces"]
        for i, load in enumerate(six_loads, start=2):
            await pick_room_load(page, "Kitchen", load)
            pressed = await page.locator(f'[data-field="gangPosition"] .chip[data-value="{i}"][aria-pressed="true"]').count()
            check(f"S14 slot {i} is ready after previous save", pressed > 0)
            await save(page)
        check("S14 after slot 6, gang resets to 1",
              await page.locator('[data-field="gangSize"] .chip[data-value="1"][aria-pressed="true"]').count() > 0)
        ok, actual, body = await assert_order(page, "S14 6-gang kitchen box", {
            "dimmer": 4, "onoff": 2, "fan": 0, "companion": 0, "dumb": 0,
            "plates": {6: 1}, "locations": 6, "verify": 0
        })
        check("S14 install list shows a 6-gang box", "6-gang box" in body)
        check("S14 install list has slots 1-6",
              all(f"Slot {n}" in body for n in range(1, 7)))
        await show_parts(page)
        parts = await page.inner_text("body")
        check("S14 parts list has a 6-gang wallplate", "6-gang wallplate" in parts)
        await shot(page, "393-dark-6-gang-install.png")
        async with page.expect_download() as dl:
            await page.click("#exportCsv")
        csvp = OUT / "s14-6-gang.csv"
        await (await dl.value).save_as(str(csvp))
        csv = csvp.read_text(encoding="utf-8")
        shop = await parse_csv_shop(csv)
        check("S14 CSV has 4 dimmers, 2 on/off, one 6-gang plate",
              shop.get("Smart dimmer") == 4 and shop.get("Smart on/off") == 2 and shop.get("6-gang wallplate") == 1, shop)
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-6-gang-install.png")
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)
        await page.click('[data-field="gangSize"] .chip[data-value="6"]')
        await page.wait_for_timeout(80)
        await shot(page, "393-light-6-gang-form.png")
        for width, tag in ((375, "375"), (393, "393")):
            await page.set_viewport_size({"width": width, "height": 667 if width == 375 else 852})
            await page.wait_for_timeout(80)
            ov = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
            check(f"S14 {tag} light gang chips do not overflow", ov)
            # chips should be visible and not overlapping
            fit = await page.evaluate("""() => {
              const chips = [...document.querySelectorAll('[data-field="gangSize"] .chip')];
              if (chips.length < 6) return {ok:false, n: chips.length};
              const boxes = chips.map((c) => c.getBoundingClientRect());
              if (boxes.some((b) => b.width < 8 || b.height < 24)) return {ok:false, boxes};
              for (let i = 0; i < boxes.length; i++) {
                for (let j = i + 1; j < boxes.length; j++) {
                  const a = boxes[i], b = boxes[j];
                  const overlap = a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
                  if (overlap) return {ok:false, overlap:[i,j]};
                }
              }
              return {ok:true, n: chips.length, rows: new Set(boxes.map((b) => Math.round(b.top))).size};
            }""")
            check(f"S14 {tag} light gang chips fit without crowding", bool(fit) and fit.get("ok"), fit)
            await shot(page, f"{tag}-light-6-gang-chips.png")
        await page.emulate_media(color_scheme="dark")
        await page.set_viewport_size({"width": 375, "height": 667})
        await page.wait_for_timeout(80)
        ov = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        check("S14 375 dark gang chips do not overflow", ov)
        await shot(page, "375-dark-6-gang-chips.png")
        await page.set_viewport_size({"width": 393, "height": 852})
        await page.wait_for_timeout(80)


        # 15. Unknown / find out, no 3-way grouping, summary list, accent dropdown
        await goto_walk_new_home(page, "S15 Unknown switches")
        await page.set_viewport_size({"width": 393, "height": 852})
        opts = await page.locator("#loadType option").all_text_contents()
        real = [o.strip() for o in opts if o.strip() and "Type or choose" not in o]
        check("S15 Unknown is the first type in the dropdown", real[0] == "Unknown / find out", real[:4])
        check("S15 Accent lights is in the dropdown", "Accent lights" in opts)
        await page.select_option("select[data-field='room']", "Kitchen")
        await page.select_option("#loadType", "Unknown")
        await page.wait_for_timeout(80)
        body = await page.inner_text("body")
        check("S15 picking Unknown fills the label", "Unknown / find out" in (await page.locator("#loadQuery").input_value() or "") or "Unknown" in body)
        check("S15 Unknown does not prompt Same/New before save", not await has_same_or_new(page))
        await set_gang(page, 2, 1)
        await open_more(page)
        await page.fill('textarea[data-field="note"]', "switch cover")
        await save(page)
        check("S15 first Unknown saves with no Same/New", not await has_same_or_new(page))
        check("S15 after Unknown save, slot advances",
              await page.locator('[data-field="gangPosition"] .chip[data-value="2"][aria-pressed="true"]').count() > 0)
        await page.select_option("select[data-field='room']", "Kitchen")
        await page.select_option("#loadType", "Unknown")
        await page.wait_for_timeout(80)
        await save(page)
        check("S15 second Unknown saves with no Same/New", not await has_same_or_new(page))
        body = await page.inner_text("body")
        check("S15 survey order has Unknown badges", body.count("Unknown") >= 2)
        check("S15 unknowns did not become a 3-way", "3-way" not in body and "Linked as a 3-way" not in body)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("S15 Unknowns to identify is on Summary", "Unknowns to identify" in body)
        check("S15 unknown list has floor, room, box, slot, and note",
              "Kitchen" in body and "2-gang box, slot 1" in body and "switch cover" in body and "slot 2" in body)
        check("S15 install list badges Unknown", "Unknown" in body and "identify on site" in body.lower())
        await show_parts(page)
        q = await qty_on(page)
        check("S15 unknowns are not on the parts order",
              q.get("Smart dimmer", 0) == 0 and q.get("Smart on/off", 0) == 0, q)
        await shot(page, "393-dark-unknown-summary.png")
        async with page.expect_download() as dl:
            await page.click("#exportInstallCsv")
        csvp = OUT / "s15-unknown-install.csv"
        await (await dl.value).save_as(str(csvp))
        csv = csvp.read_text(encoding="utf-8")
        check("S15 install CSV marks Unknown and keeps the note", "Unknown" in csv and "switch cover" in csv, csv[:500])
        async with page.expect_download() as dl2:
            await page.click("#exportCsv")
        csv2 = (await dl2.value).path()
        shopcsv = Path(csv2).read_text(encoding="utf-8") if False else (OUT / "s15-unknown-order.csv")
        # playwright download path — save explicitly
        await (await dl2.value).save_as(str(OUT / "s15-unknown-order.csv"))
        order_csv = (OUT / "s15-unknown-order.csv").read_text(encoding="utf-8")
        check("S15 order CSV has Unknowns to identify", "UNKNOWNS TO IDENTIFY" in order_csv and "switch cover" in order_csv, order_csv[-800:])

        # Dropdown still shows Same light as… when a known type is picked
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)
        await pick_room_load(page, "Living room", "Accent lights")
        await save(page)
        await page.select_option("select[data-field='room']", "Office")
        await page.select_option("#loadType", "Accent lights")
        await page.wait_for_timeout(120)
        same = await page.inner_text("#sameLightSuggest")
        check("S15 dropdown pick shows Same light as Accent lights",
              "Same light as Accent lights" in same and "Living room" in same, same)
        await shot(page, "393-dark-accent-suggestions.png")
        # don't save this second accent (would prompt Same/New — that's correct)

        # Keyboard: type "unknown" to mark a switch
        await page.click("#clearDraft")
        await page.wait_for_timeout(80)
        await page.select_option("select[data-field='room']", "Hall")
        await page.locator("#loadQuery").click()
        await page.locator("#loadQuery").fill("unknown")
        await page.locator("#loadQuery").press("Enter")
        await page.wait_for_timeout(120)
        check("S15 typing unknown selects Unknown / find out",
              (await page.locator("#loadType").input_value()) == "Unknown"
              or "Unknown / find out" in (await page.locator("#loadQuery").input_value() or ""))
        await save(page)
        check("S15 typed Unknown saves with no Same/New", not await has_same_or_new(page))
        await shot(page, "393-dark-unknown-walk.png")

        await page.emulate_media(color_scheme="light")
        await page.set_viewport_size({"width": 393, "height": 852})
        await page.wait_for_timeout(80)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(150)
        await shot(page, "393-light-unknown-summary.png")
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-unknown-form.png")
        for width, tag in ((375, "375"), (393, "393")):
            await page.set_viewport_size({"width": width, "height": 667 if width == 375 else 852})
            await page.wait_for_timeout(80)
            ov = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
            check(f"S15 {tag} light type dropdown does not overflow", ov)
            await page.locator("#loadQuery").click()
            await page.wait_for_timeout(80)
            await shot(page, f"{tag}-light-unknown-keyboard.png")
            await page.locator("h1").click()
            await page.wait_for_timeout(80)
        await page.emulate_media(color_scheme="dark")
        await page.set_viewport_size({"width": 375, "height": 667})
        await page.wait_for_timeout(80)
        await shot(page, "375-dark-unknown-form.png")
        await page.locator("#loadQuery").click()
        await page.wait_for_timeout(80)
        await shot(page, "375-dark-unknown-keyboard.png")
        await page.locator("h1").click()
        await page.set_viewport_size({"width": 393, "height": 852})
        await page.wait_for_timeout(80)


        # 16. Ring camera: always on, not ordered, can still Same/New
        await goto_walk_new_home(page, "S16 Ring camera")
        await page.set_viewport_size({"width": 393, "height": 852})
        opts = await page.locator("#loadType option").all_text_contents()
        check("S16 Ring camera is in the dropdown", "Ring camera" in opts)
        await pick_room_load(page, "Kitchen", "Ring camera")
        body = await page.inner_text("body")
        check("S16 preview says keep always on", "keep always on" in body.lower() and "smart switch or dimmer" in body.lower())
        await save(page)
        check("S16 first Ring camera has no Same/New", not await has_same_or_new(page))
        await pick_room_load(page, "Kitchen", "Ring camera")
        await save(page)
        check("S16 second Ring camera prompts Same/New", await has_same_or_new(page))
        await click_same_light(page, "Kitchen")
        body = await page.inner_text("body")
        check("S16 same-light grouping works", "3-way" in body or "Linked as a 3-way" in body)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        await show_parts(page)
        body = await page.inner_text("body")
        check("S16 install list flags keep always on", "Keep always on, don't put on a smart switch or dimmer" in body or "keep always on, don't put on a smart switch or dimmer" in body.lower())
        q = await qty_on(page)
        check("S16 Ring cameras are not on the parts order",
              q.get("Smart dimmer", 0) == 0 and q.get("Smart on/off", 0) == 0 and q.get("Companion", 0) == 0, q)
        await shot(page, "393-dark-ring-camera-install.png")
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-ring-camera-install.png")
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(80)


        # 17. Light is in: Hall switch controlling Kitchen cans
        await goto_walk_new_home(page, "S17 Light location")
        await page.set_viewport_size({"width": 393, "height": 852})
        check("S17 Light is in is on the form", await page.locator("#lightPlace").count() > 0)
        await pick_room_load(page, "Kitchen", "Can lights")
        same_opt = await page.locator("#lightPlace option[value='same']").text_content()
        check("S17 defaults to Kitchen (same as switch)", "Kitchen" in (same_opt or "") and "same as switch" in (same_opt or "").lower(), same_opt)
        check("S17 Yard is in the Outside options", await page.locator("#lightPlace option[value='Exterior|Yard']").count() > 0)
        check("S17 Front porch is in the Outside options", await page.locator("#lightPlace option[value='Exterior|Front porch']").count() > 0)
        await save(page)
        await pick_room_load(page, "Hall", "Can lights")
        same_opt = await page.locator("#lightPlace option[value='same']").text_content()
        check("S17 Hall switch still defaults to Hall", "Hall" in (same_opt or "") and "same as switch" in (same_opt or "").lower(), same_opt)
        await set_light_place(page, "Kitchen")
        check("S17 Light is in can be changed to Kitchen in one tap", (await page.locator("#lightPlace").input_value()) == "Main|Kitchen")
        body = await page.inner_text("body")
        check("S17 preview names the light in Kitchen", "in Kitchen" in body, body[-400:])
        await save(page)
        # explicit light location + exact match may auto-join or prompt Same/New
        if await has_same_or_new(page):
            await click_same_light(page, "Kitchen")
        body = await page.inner_text("body")
        check("S17 Hall switch groups with Kitchen cans", "3-way" in body or "Linked as a 3-way" in body, body[-500:])
        check("S17 survey order says Can lights (in Kitchen)", "Can lights (in Kitchen)" in body)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("S17 install list flags Can lights (in Kitchen)", "Can lights (in Kitchen)" in body)
        q = await qty_on(page)
        check("S17 parts are 1 dimmer + 1 companion, not two dimmers",
              q.get("Smart dimmer", 0) == 1 and q.get("Companion", 0) == 1, q)
        await shot(page, "393-dark-light-in-kitchen.png")
        async with page.expect_download() as dl:
            await page.click("#exportInstallCsv")
        csvp = OUT / "s17-light-in-install.csv"
        await (await dl.value).save_as(str(csvp))
        csv = csvp.read_text(encoding="utf-8")
        check("S17 install CSV has Can lights (in Kitchen)", "Can lights (in Kitchen)" in csv, csv[:800])
        # Exterior label
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)
        await pick_room_load(page, "Hall", "Exterior lights")
        await set_light_place(page, "Front porch", floor="Exterior")
        body = await page.inner_text("body")
        check("S17 porch preview uses Outside, Front porch", "Outside, Front porch" in body, body[-400:])
        await save(page)
        body = await page.inner_text("body")
        check("S17 survey lists Exterior lights (Outside, Front porch)", "Exterior lights (Outside, Front porch)" in body, body[-600:])
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(80)
        body = await page.inner_text("body")
        check("S17 light theme install list has in Kitchen", "Can lights (in Kitchen)" in body)
        await shot(page, "393-light-light-in-kitchen.png")
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(80)


        # 18. Kitchen Chandelier must not auto-pick Family room Chandelier
        await goto_walk_new_home(page, "S18 Chandelier rooms")
        await page.set_viewport_size({"width": 393, "height": 852})
        await pick_room_load(page, "Family room", "Chandelier")
        await save(page)
        await pick_room_load(page, "Kitchen", "Chandelier")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("S18 shows Same light as Family room Chandelier",
              "Same light as Chandelier (in Family room)" in body, body[-500:])
        pressed = await page.locator("[data-pick-light][aria-pressed='true']").count()
        check("S18 Same light chip is not pre-selected", pressed == 0, pressed)
        check("S18 New light chip is visible", await page.locator("#suggestNewLight").count() > 0 and await page.locator("#suggestNewLight").is_visible())
        preview = await page.locator(".auto").inner_text() if await page.locator(".auto").count() else body
        check("S18 preview does not treat it as the Family room light",
              "Family room" not in preview and "switch →" not in preview, preview)
        same_opt = await page.locator("#lightPlace option[value='same']").text_content() if await page.locator("#lightPlace").count() else ""
        check("S18 Light is in stays Kitchen (same as switch)",
              "Kitchen" in (same_opt or "") and (await page.locator("#lightPlace").input_value()) == "same", same_opt)
        await save(page)
        check("S18 saving without tapping does not prompt Same/New for the other room", not await has_same_or_new(page))
        body = await page.inner_text("body")
        check("S18 did not auto-link Kitchen and Family room chandeliers",
              "3-way" not in body and "Linked as a 3-way" not in body, body[-600:])
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        await show_parts(page)
        q = await qty_on(page)
        check("S18 two separate dimmers, no companion",
              q.get("Smart dimmer", 0) == 2 and q.get("Companion", 0) == 0, q)
        await shot(page, "393-dark-chandelier-not-autolink.png")
        # Tapping Same light still links when he means it
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)
        await goto_walk_new_home(page, "S18 Chandelier link")
        await pick_room_load(page, "Family room", "Chandelier")
        await save(page)
        await pick_room_load(page, "Kitchen", "Chandelier")
        await pick_existing_light(page, "Same light as Chandelier (in Family room")
        body = await page.inner_text("body")
        check("S18 after tap, preview can name the Family room light", "Family room" in body)
        await save(page)
        body = await page.inner_text("body")
        check("S18 tap Same light still links as a 3-way", "3-way" in body or "Linked as a 3-way" in body)
        await shot(page, "393-dark-chandelier-tapped-link.png")
        # New light keeps them separate
        await goto_walk_new_home(page, "S18 Chandelier new")
        await pick_room_load(page, "Family room", "Chandelier")
        await save(page)
        await pick_room_load(page, "Kitchen", "Chandelier")
        await page.wait_for_timeout(500)
        await page.click("#suggestNewLight")
        await page.wait_for_timeout(200)
        await save(page)
        check("S18 New light saves with no Same/New prompt", not await has_same_or_new(page))
        body = await page.inner_text("body")
        check("S18 New light did not 3-way", "3-way" not in body and "Linked as a 3-way" not in body)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("S18 New light orders two dimmers",
              q.get("Smart dimmer", 0) == 2 and q.get("Companion", 0) == 0, q)
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-chandelier-new.png")
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(80)

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
        check("light walk form shows tagged light chips", "same light as sink" in body.lower() and "same light as #2" in body.lower())
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

        # Light first launch and empty survey form (fresh profile)
        light_ctx = await browser.new_context(viewport={"width": 393, "height": 852}, color_scheme="light", device_scale_factor=2)
        light_page = await light_ctx.new_page()
        await light_page.goto(BASE, wait_until="load")
        await light_page.wait_for_selector("[data-tab='walk']")
        lbody = await light_page.inner_text("body")
        check("light first launch has no PIN screen",
              await light_page.locator("#keypad").count() == 0 and "Set a PIN" not in lbody and "Enter PIN" not in lbody)
        check("light first launch is the survey form", "Add a switch" in lbody and "Save switch" in lbody)
        check("light form has Keep as is (not smart)", "Keep as is (not smart)" in lbody and "Regular switch" not in lbody)
        await shot(light_page, "393-light-first-launch.png")
        await pick_room_load(light_page, "Kitchen", "Can lights")
        await shot(light_page, "393-light-survey-form.png")
        await light_ctx.close()

        # clear
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
