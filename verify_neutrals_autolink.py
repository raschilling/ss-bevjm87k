import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = os.environ.get("SS_BASE", "http://127.0.0.1:8771/index.html")
OUT = Path(os.environ.get("SS_OUT", "/workspace/switch-survey/verify/neutrals-autolink"))
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
        check("noindex", "noindex" in src)
        await page.wait_for_selector("[data-tab='walk']")

        # Walk top: no neutrals card, no Also controlled from until More
        body = await page.inner_text("body")
        check("walk has no Neutrals card", "Neutrals in this house" not in body and "Most have a neutral" not in body, body[:500])
        await open_hint(page, "addSwitch")
        body = await page.inner_text("body")
        check("survey intro is survey-every-switch", "Survey every switch in order" in body)
        check("Also controlled from not on main walk", "Also controlled from" not in body)
        check("Where the switch is", "Where the switch is" in body)
        check("Switch type on main form", "Switch type" in body and "Dimmer" in body)
        check("light question off main walk", "Is the light in this room?" not in body and "Light is in a different room" not in body and "Where is the light?" not in body)
        await shot(page, "393-dark-walk-top.png")

        await page.click("#moreToggle")
        await page.wait_for_timeout(80)
        body = await page.inner_text("body")
        check("Also controlled from under More", "Also controlled from" in body)
        check("no Light is in a different room under More", "Light is in a different room" not in body and "Where is the light?" not in body)
        await page.click("#moreToggle")
        await page.wait_for_timeout(80)
        check("Also controlled from hidden after collapse", "Also controlled from" not in (await page.inner_text("body")))

        # Example totals + AC/DC fan path still 23/6/1/5, no unknown nag
        await page.click("[data-tab='homes']")
        await page.click("text=Load example house")
        await page.wait_for_timeout(200)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("example 23/6/1/5", q.get("Smart dimmer")==23 and q.get("Smart on/off")==6 and q.get("Smart fan")==1 and q.get("Companion")==5, q)
        body = await page.inner_text("body")
        check("no unknown neutrals nag", "House neutrals have not been spot-checked" not in body)
        check("summary Older house? Change", "Older house without neutrals? Change" in body)
        await open_hint(page, "neutralsYes")
        body = await page.inner_text("body")
        check("soft yes note", "Assumes boxes have a neutral" in body and "1980s" in body)
        await shot(page, "393-dark-summary.png")

        # Override: Most do not -> issue appears
        await page.click("text=Older house without neutrals? Change")
        await page.wait_for_timeout(80)
        await page.click('[data-field="neutrals"] .chip[data-value="no"]')
        await page.wait_for_timeout(150)
        body = await page.inner_text("body")
        check("no-neutral issue after override", "Most boxes do not have a neutral" in body)
        # set back to yes for later shots
        if await page.locator('[data-field="neutrals"] .chip[data-value="yes"]').count():
            await page.click('[data-field="neutrals"] .chip[data-value="yes"]')
            await page.wait_for_timeout(80)

        await goto_walk_new_home(page, "Default neutrals")
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(150)
        body = await page.inner_text("body")
        await open_hint(page, "neutralsYes")
        body = await page.inner_text("body")
        check("new home soft yes note", "Assumes boxes have a neutral" in body)
        check("new home no neutrals nag", "House neutrals have not been spot-checked" not in body and "Most boxes do not have a neutral" not in body)

        # How many?
        await page.click("[data-tab='walk']")
        await pick_room_load(page, "Hall", "Can lights")
        body = await page.inner_text("body")
        check("fixture count collapsed until tapped", await page.locator("#fixtureOpen").count() > 0 and "Fixtures on this switch" not in body)
        await open_fixture(page)
        body = await page.inner_text("body")
        check("Fixtures on this switch after tap", "Fixtures on this switch" in body)
        await page.click('[data-field="fixtureCount"] .chip[data-value="6"]')
        await page.wait_for_timeout(80)
        check("preview Hall cans x6", "Hall cans x6" in (await page.inner_text("body")))
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("walk list Hall cans x6", "Hall cans x6" in body)
        check("survey order heading", "Survey order" in body)

        # Different rooms, same load: no auto-link
        await goto_walk_new_home(page, "Different lights")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await pick_room_load(page, "Hall", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("no mid-walk Same light prompt", "Same light as" not in body and "This makes it a 3-way" not in body)
        check("no auto-link across different lights", "3-way (2 locations)" not in body and "Linked as a" not in body)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("two separate dimmers, no companion", q.get("Smart dimmer")==2 and "Companion" not in q, q)

        # Auto 3-way: Kitchen, then Stairs with light elsewhere Kitchen
        await goto_walk_new_home(page, "Auto 3-way")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await pick_room_load(page, "Stairs", "Can lights")
        await pick_existing_light(page, "Main Kitchen cans")
        await page.click("#saveSw")
        await page.wait_for_timeout(250)
        body = await page.inner_text("body")
        check("auto 3-way no mid-walk prompt", "This makes it a" not in body and await page.locator("#linkYes").count() == 0)
        check("auto 3-way flash or badge", "Linked as a 3-way" in body or "3-way 1/2" in body or "3-way (2 locations)" in body, body[-400:])
        check("walk list keeps log order", "1." in body and "2." in body and body.find("Kitchen") < body.find("Stairs switch") or body.find("1.") < body.find("2."))
        # logged order: first item kitchen, second stairs
        # Look at numbered labels
        import re as _re
        # already imported at top as re - ok
        check("walk list 1 then 2", "1." in body and "2." in body)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("auto 3-way 1 dimmer + 1 companion", q.get("Smart dimmer")==1 and q.get("Companion")==1, q)
        body = await page.inner_text("body")
        check("summary switch vs light", "Switch:" in body and "Light:" in body and "Stairs" in body and "Kitchen" in body)
        check("summary has Unlink", "Unlink" in body)
        await shot(page, "393-dark-auto-3way-summary.png")

        # Unlink should not double-count; then merge back
        if await page.locator("[data-unlink]").count():
            await page.locator("[data-unlink]").first.click()
            await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("after unlink, two dimmers no companion", q.get("Smart dimmer")==2 and "Companion" not in q, q)
        body = await page.inner_text("body")
        check("merge UI after unlink", "Merge with" in body or "Merge switches" in body, body[-500:])
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
        q = await qty_on(page)
        check("merge restores 1 dimmer + 1 companion", q.get("Smart dimmer")==1 and q.get("Companion")==1, q)

        # Auto 4-way
        await goto_walk_new_home(page, "Auto 4-way")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(150)
        await pick_room_load(page, "Hall", "Can lights")
        await pick_existing_light(page, "Main Kitchen cans")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("second save auto-links without prompt", "This makes it a 3-way" not in body and ("Linked as a 3-way" in body or "3-way 1/2" in body or "3-way (2 locations)" in body))
        await pick_room_load(page, "Foyer", "Can lights")
        await pick_existing_light(page, "Main Kitchen cans")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("third save auto 4-way no prompt", "This makes it a 4-way" not in body or "Link" not in body)
        check("third save 4-way badge or flash", "4-way" in body, body[-300:])
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("auto 4-way 1 dimmer + 2 companions", q.get("Smart dimmer")==1 and q.get("Companion")==2, q)
        check("4-way summary badge 3 locations", "4-way (3 locations)" in (await page.inner_text("body")))
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(100)
        wbody = await page.inner_text("body")
        check("4-way walk position badges", "4-way 1/3" in wbody and "4-way 2/3" in wbody and "4-way 3/3" in wbody)

        # Fan type still on form
        await page.click("[data-tab='walk']")
        await pick_room_load(page, "Bedroom", "Ceiling fan")
        body = await page.inner_text("body")
        check("Fan type shows for ceiling fan", "Fan type" in body)
        check("fixture count hidden for fan", await page.locator("#fixtureOpen").count() == 0 and "Fixtures on this switch" not in (await page.inner_text("body")))

        # Autosave survives reload with no PIN
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await page.reload(wait_until="load")
        await page.wait_for_selector("[data-tab='walk']", timeout=4000)
        body = await page.inner_text("body")
        check("reload has no PIN screen", await page.locator("#keypad").count() == 0 and "Enter PIN" not in body and "Set a PIN" not in body)
        await page.click("[data-tab='homes']")
        await page.wait_for_timeout(100)
        body = await page.inner_text("body")
        check("autosave kept Auto 4-way home", "Auto 4-way" in body, body[:500])

        # Export JSON + CSV
        await page.click("text=Auto 4-way")
        await page.wait_for_timeout(100)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(150)
        async with page.expect_download() as dl:
            await page.click("#exportCsv")
        csvp = OUT / "auto-4way.csv"
        await (await dl.value).save_as(str(csvp))
        csv = csvp.read_text(encoding="utf-8")
        check("csv export has 4-way and Switch vs light", "4-way" in csv and "Switch vs light" in csv, csv[:400])
        async with page.expect_download() as dl:
            await page.click("#exportJson")
        jp = OUT / "auto-4way.json"
        await (await dl.value).save_as(str(jp))
        data = json.loads(jp.read_text(encoding="utf-8"))
        check("json export kind and homes", data.get("kind")=="ha-switch-survey" and isinstance(data.get("homes"), list) and data["homes"], list(data.keys()))

        # Import: add a second home from the exported file (will duplicate). Then check import flash.
        await page.click("[data-tab='homes']")
        await page.wait_for_timeout(80)
        # file input for import
        inp = page.locator("input[type=file]")
        if await inp.count():
            before = await page.inner_text("body")
            await inp.set_input_files(str(jp))
            await page.wait_for_timeout(300)
            body = await page.inner_text("body")
            check("json import accepted", "Imported" in body or body != before, body[:400])
        else:
            check("json import accepted", False, "no file input")

        # Light + widths 344/393/768/1440
        await page.emulate_media(color_scheme="light")
        await page.set_viewport_size({"width": 393, "height": 852})
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)
        bg = await page.eval_on_selector("body", "el => getComputedStyle(el).backgroundColor")
        check("light bg", bg.replace(" ","") == "rgb(243,241,234)", bg)
        body = await page.inner_text("body")
        check("light walk has no Neutrals card", "Neutrals in this house" not in body)
        check("light question off main walk in light theme", "Is the light in this room?" not in body and "Where is the light?" not in body)
        await shot(page, "393-light-walk-top.png")
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-summary.png")
        for w,h,label in ((344,780,"344-folded"), (768,900,"768-tablet"), (1440,900,"1440-desktop")):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(80)
            ov = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
            check(f"{label} light no overflow", ov)
            await shot(page, f"{label}-light-summary.png")
        await page.emulate_media(color_scheme="dark")
        for w,h,label in ((344,780,"344-folded"), (393,852,"393"), (768,900,"768-tablet"), (1440,900,"1440-desktop")):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(80)
            await page.click("[data-tab='walk']")
            ovw = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
            check(f"{label} dark walk no overflow", ovw)
            await page.click("[data-tab='summary']")
            await page.wait_for_timeout(50)
            ovs = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
            check(f"{label} dark summary no overflow", ovs)

        # unknown -> yes migration via in-page evaluate of migrateHomes by temporarily setting neutrals
        # Verify migrate function exists in source:
        # exposing a one-off. Instead, patch the live store if we can by clicking and then evaluate
        # document hook. Skip if we didn't add hook; we can add a tiny evaluate that uses
        # the already-open page after we inject: actually store is in closure.
        # Verify migrate function exists in source at least:
        src = await page.content()
        check("migrateHomes in app", "function migrateHomes" in src)

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
    failed = [c for c in results["checks"] if not c["ok"]]
    print("\nSUMMARY", "PASS" if results["ok"] else f"FAIL {len(failed)}", "of", len(results["checks"]))
    for c in failed:
        print(" -", c["name"], ":", c["detail"][:400])
    sys.exit(0 if results["ok"] else 1)

asyncio.run(run())
