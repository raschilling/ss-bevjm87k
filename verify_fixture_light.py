import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = os.environ.get("SS_BASE", "http://127.0.0.1:8770/index.html")
OUT = Path(os.environ.get("SS_OUT", "/workspace/switch-survey/verify/fixture-light"))
OUT.mkdir(parents=True, exist_ok=True)
WEBKIT = "/home/box/.cache/ms-playwright/webkit-2388/pw_run.sh"
results = {"ok": True, "base": BASE, "checks": []}

def check(name, cond, detail=""):
    results["checks"].append({"name": name, "ok": bool(cond), "detail": str(detail)})
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not cond:
        results["ok"] = False

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

async def pick_room_load(page, room, load):
    await page.select_option("select[data-field='room']", room)
    await page.select_option("select[data-field='load']", load)
    await page.wait_for_timeout(80)

async def open_more(page):
    more = page.locator("#more")
    if await more.count() and "hidden" in ((await more.get_attribute("class")) or "").split():
        await page.click("#moreToggle")
        await page.wait_for_timeout(80)

async def open_hint(page, hint_id):
    btn = page.locator(f'[data-toggle-hint="{hint_id}"]')
    if await btn.count() and (await btn.get_attribute("aria-expanded")) != "true":
        await btn.click()
        await page.wait_for_timeout(60)

async def open_fixture(page):
    if await page.locator("#fixtureOpen").count():
        await page.click("#fixtureOpen")
        await page.wait_for_timeout(60)


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



async def run():
    async with async_playwright() as p:
        browser = await p.webkit.launch(executable_path=WEBKIT)
        ctx = await browser.new_context(viewport={"width": 393, "height": 852}, color_scheme="dark", device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(BASE, wait_until="load")
        await page.wait_for_selector("h1")
        check("title", await page.title() == "Switch Survey")
        src = await page.content()
        check("noindex", 'noindex' in src)
        await page.wait_for_selector("[data-tab='walk']")
        body = await page.inner_text("body")
        check("Where the switch is", "Where the switch is" in body)
        await open_hint(page, "floor")
        body = await page.inner_text("body")
        check("switch location hint", "where this switch is" in body.lower())
        check("light question off main walk", "Is the light in this room?" not in body and "Light is in a different room" not in body and "Where is the light?" not in body)
        check("Switch type on main form", "Switch type" in body and "Dimmer" in body)
        check("fixture count hidden until multi load", await page.locator("#fixtureOpen").count() == 0 and "Fixtures on this switch" not in body)
        await shot(page, "393-dark-walk-start.png")

        # Example house totals unchanged
        await page.click("[data-tab='homes']")
        await page.click("text=Load example house")
        await page.wait_for_timeout(200)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("example 23/6/1/5", q.get("Smart dimmer")==23 and q.get("Smart on/off")==6 and q.get("Smart fan")==1 and q.get("Companion")==5, q)
        await shot(page, "393-dark-example-summary.png")

        # Fixture count
        await goto_walk_new_home(page, "Fixture hall")
        await pick_room_load(page, "Hall", "Can lights")
        body = await page.inner_text("body")
        check("fixture count collapsed until tapped", await page.locator("#fixtureOpen").count() > 0 and "Fixtures on this switch" not in body)
        await open_fixture(page)
        body = await page.inner_text("body")
        check("Fixtures on this switch after tap", "Fixtures on this switch" in body)
        check("fixture chips 1-8 and 8+", all(x in body for x in ["1","2","6","8","8+"]))
        await page.click('[data-field="fixtureCount"] .chip[data-value="6"]')
        await page.wait_for_timeout(80)
        body = await page.inner_text("body")
        check("preview Hall cans x6", "Hall cans x6" in body, body[body.find("Hall"):body.find("Hall")+80] if "Hall" in body else body[-200:])
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("walk list Hall cans x6", "Hall cans x6" in body)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("wattage note when count is 6+", "wattage" in body.lower() and "Hall cans x6" in body, body[-400:])
        q = await qty_on(page)
        check("fixture home 1 dimmer", q.get("Smart dimmer")==1 and "Companion" not in q, q)
        await shot(page, "393-dark-fixture-summary.png")
        async with page.expect_download() as dl:
            await page.click("#exportCsv")
        csvp = OUT / "fixture-hall.csv"
        await (await dl.value).save_as(str(csvp))
        csv = csvp.read_text(encoding="utf-8")
        check("csv Fixtures header", "Fixtures" in csv)
        check("csv fixture count 6", ",6," in csv or ",6\n" in csv)
        check("csv wattage issue", "wattage" in csv.lower())

        # Ceiling fan does not show How many?
        await page.click("[data-tab='walk']")
        await pick_room_load(page, "Bedroom", "Ceiling fan")
        body = await page.inner_text("body")
        check("fixture count hidden for ceiling fan", await page.locator("#fixtureOpen").count() == 0 and "Fixtures on this switch" not in (await page.inner_text("body")))
        check("Fan type shows when Fan selected", "Fan type" in body)

        # Kitchen cans vs Hall cans should NOT auto-link
        await goto_walk_new_home(page, "Different lights")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await pick_room_load(page, "Hall", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("same-floor different rooms do not auto-link", "Same light as" not in body and "This makes it a 3-way" not in body)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("two separate dimmers, no companion", q.get("Smart dimmer")==2 and "Companion" not in q, q)

        # 3-way: switch in Stairs, light in Kitchen, matches Kitchen cans
        await goto_walk_new_home(page, "Light elsewhere 3-way")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await pick_room_load(page, "Stairs", "Can lights")
        check("Kitchen cans chip on Stairs form", "Main Kitchen cans" in (await page.inner_text("body")))
        await pick_existing_light(page, "Main Kitchen cans")
        body = await page.inner_text("body")
        check("preview shows switch then light", "Stairs switch" in body and "Kitchen" in body)
        await shot(page, "393-dark-light-elsewhere-form.png")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("cross-room auto-links via chip, no prompt", "This makes it a" not in body and await page.locator("#linkYes").count() == 0)
        check("linked walk badge 3-way", "3-way 1/2" in body or "Linked as a 3-way" in body or "3-way (2 locations)" in body, body[-500:])
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("cross-room 1 dimmer + 1 companion", q.get("Smart dimmer")==1 and q.get("Companion")==1, q)
        body = await page.inner_text("body")
        check("summary shows switch vs light", "Switch:" in body and "Light:" in body and "Stairs" in body and "Kitchen" in body, body)
        await shot(page, "393-dark-cross-room-summary.png")
        async with page.expect_download() as dl:
            await page.click("#exportCsv")
        csvp = OUT / "light-elsewhere.csv"
        await (await dl.value).save_as(str(csvp))
        csv = csvp.read_text(encoding="utf-8")
        check("csv Switch vs light header", "Switch vs light" in csv)
        check("csv switch vs light value", "Switch:" in csv and "Light:" in csv and "Stairs" in csv and "Kitchen" in csv, csv[csv.find("BY FLOOR"):csv.find("BY FLOOR")+800] if "BY FLOOR" in csv else csv[-500:])

        # 4-way: three switches, same light in Kitchen
        await goto_walk_new_home(page, "Light elsewhere 4-way")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(150)
        await pick_room_load(page, "Hall", "Can lights")
        await pick_existing_light(page, "Main Kitchen cans")
        await page.click("#saveSw")
        await page.wait_for_timeout(150)
        body = await page.inner_text("body")
        check("second end auto-links 3-way via chip", "This makes it a 3-way" not in body and ("Linked as a 3-way" in body or "3-way 1/2" in body or "3-way (2 locations)" in body))
        await pick_room_load(page, "Foyer", "Can lights")
        await pick_existing_light(page, "Main Kitchen cans")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("third end auto-links 4-way via chip", "This makes it a 4-way" not in body and ("Linked as a 4-way" in body or "4-way 1/3" in body or "4-way (3 locations)" in body), body)
        await page.wait_for_timeout(200)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("4-way 1 dimmer + 2 companions", q.get("Smart dimmer")==1 and q.get("Companion")==2, q)
        check("4-way summary badge 3 locations", "4-way (3 locations)" in (await page.inner_text("body")))
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(100)
        wbody = await page.inner_text("body")
        check("4-way walk position badges", "4-way 1/3" in wbody and "4-way 2/3" in wbody and "4-way 3/3" in wbody)
        await shot(page, "393-dark-four-way-light.png")

        # Autosave survives reload with no PIN
        await page.reload(wait_until="load")
        await page.wait_for_selector("[data-tab='walk']", timeout=4000)
        body = await page.inner_text("body")
        check("reload has no PIN screen", await page.locator("#keypad").count() == 0 and "Enter PIN" not in body and "Set a PIN" not in body)
        await shot(page, "393-dark-after-reload.png")

        # Light theme + widths
        await page.emulate_media(color_scheme="light")
        await page.set_viewport_size({"width": 393, "height": 852})
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)
        bg = await page.eval_on_selector("body", "el => getComputedStyle(el).backgroundColor")
        check("light bg", bg.replace(" ","") == "rgb(243,241,234)", bg)
        check("light Where the switch is", "Where the switch is" in (await page.inner_text("body")))
        await shot(page, "393-light-walk.png")
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-summary.png")
        for w,h,label in ((840,820,"840-unfolded"), (1440,900,"1440-desktop")):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(80)
            ov = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
            check(f"{label} light no overflow", ov)
            await shot(page, f"{label}-light-summary.png")

        # clear test data
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
        print(" -", c["name"], c["detail"])
    sys.exit(0 if results["ok"] else 1)

asyncio.run(run())
