import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright
from verify_helpers import choose_load, pick_existing_light, open_more, set_other_spots, show_parts

BASE = os.environ.get("SS_BASE", "http://127.0.0.1:8768/index.html")
OUT = Path(os.environ.get("SS_OUT", "/workspace/switch-survey/verify/ways"))
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

async def pick_room_load(page, room, load):
    await page.select_option("select[data-field='room']", room)
    await choose_load(page, load)
    await page.wait_for_timeout(80)

async def run():
    async with async_playwright() as p:
        browser = await p.webkit.launch(executable_path=WEBKIT)
        ctx = await browser.new_context(viewport={"width": 393, "height": 852}, color_scheme="dark", device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(BASE, wait_until="load")
        await page.wait_for_selector("h1")
        await page.wait_for_function("() => document.title === 'Switch Survey'", timeout=8000)
        body = await page.inner_text("body")
        src = await page.content()
        check("title", await page.title() == "Switch Survey")
        check("no Qualifier label", "Qualifier" not in body)
        await page.wait_for_selector("[data-tab='walk']")
        body = await page.inner_text("body")
        check("Which one? is not on the form", "Which one?" not in body)
        check("Lights already logged box is gone", "Lights already logged" not in body)
        check("gang count is on the main form", "Switches in this box" in body)
        check("Also controlled from and doorway are gone", "Also controlled from" not in body and "Doorway or wall" not in body)
        await shot(page, "393-dark-walk-labels.png")

        # Example totals still include 5 companions from linked-only stairs/etc.
        await page.click("[data-tab='homes']")
        await page.click("text=Load example house")
        await page.wait_for_timeout(200)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("install list is the default summary view", "Install list" in body and "Print / Save PDF" in body and "Show parts to order" in body)
        check("install list shows boxes and other ends", "-gang box" in body and "3-way 1/2" in body and "other end" in body.lower())
        await shot(page, "393-dark-install-list.png")
        q = await qty_on(page)
        check("example 23/6/1/5", q.get("Smart dimmer")==23 and q.get("Smart on/off")==6 and q.get("Smart fan")==1 and q.get("Companion")==5, q)
        body = await page.inner_text("body")
        check("example 4-way badge (3 locations)", "4-way (3 locations)" in body)
        check("example 3-way badge (2 locations)", "3-way (2 locations)" in body)
        await page.click('[data-toggle-hint="groups"]')
        await page.wait_for_timeout(80)
        body = await page.inner_text("body")
        check("summary 4-way math hint", "1 smart switch + 2 companions" in body)
        await shot(page, "393-dark-example-summary.png")
        # walk list badges
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(100)
        body = await page.inner_text("body")
        check("walk list 4-way position badges", "4-way 1/3" in body and "4-way 2/3" in body and "4-way 3/3" in body)
        check("walk list has 3-way position badges", "3-way 1/2" in body and "3-way 2/2" in body)
        check("walk list no N locations badge", "4-way (3 locations)" not in body and "3-way (2 locations)" not in body)
        await shot(page, "393-dark-example-walk.png")
        await shot(page, "393-dark-survey-order-badges.png")
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-example-walk.png")
        await shot(page, "393-light-survey-order-badges.png")
        bg = await page.eval_on_selector("body", "el => getComputedStyle(el).backgroundColor")
        check("light survey-order bg", bg.replace(" ","") == "rgb(243,241,234)", bg)
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(80)

        # Declared-only
        await goto_walk_new_home(page, "Declared only")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await set_other_spots(page, 1)
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(150)
        body = await page.inner_text("body")
        check("declared-only walk badge", "3-way 1/2" in body and "3-way (2 locations)" not in body)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("declared-only 1 dimmer + 1 companion", q.get("Smart dimmer")==1 and q.get("Companion")==1 and "Smart fan" not in q, q)
        body = await page.inner_text("body")
        check("declared-only summary badge", "3-way (2 locations)" in body)
        await shot(page, "393-dark-declared-only.png")
        async with page.expect_download() as dl:
            await show_parts(page)
            await page.click("#exportCsv")
        csvp = OUT / "declared-only.csv"
        await (await dl.value).save_as(str(csvp))
        csv = csvp.read_text(encoding="utf-8")
        check("csv Tag header", "Name,Tag,Fixtures" in csv)
        check("csv Also controlled from", "Also controlled from" in csv and "1 other spot (3-way)" in csv)
        check("csv no Qualifier header", "Qualifier" not in csv)

        # Linked-only (3-way)
        await goto_walk_new_home(page, "Linked only")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await pick_room_load(page, "Hall", "Can lights")
        await pick_existing_light(page, "Same light as Can lights (Kitchen")
        await shot(page, "393-dark-link-prompt-3way.png")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("linked-only walk 3-way position badges", "3-way 1/2" in body and "3-way 2/2" in body)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("linked-only 1 dimmer + 1 companion", q.get("Smart dimmer")==1 and q.get("Companion")==1, q)
        await shot(page, "393-dark-linked-only.png")

        # Both: declare 1 other, then link the second — still 1 companion
        await goto_walk_new_home(page, "Both declare and link")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await set_other_spots(page, 1)
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(100)
        await page.wait_for_timeout(200)
        await pick_room_load(page, "Hall", "Can lights")
        await pick_existing_light(page, "Same light as Can lights (Kitchen")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("both-path no double count (1+1)", q.get("Smart dimmer")==1 and q.get("Companion")==1, q)
        await shot(page, "393-dark-both-no-double.png")

        # 4-way: 3 linked locations = 1 smart + 2 companions
        await goto_walk_new_home(page, "Four way linked")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(150)
        await pick_room_load(page, "Hall", "Can lights")
        await pick_existing_light(page, "Same light as Can lights (Kitchen")
        await page.click("#saveSw")
        await page.wait_for_timeout(150)
        await pick_room_load(page, "Foyer", "Can lights")
        await pick_existing_light(page, "Same light as Can lights (Kitchen")
        await shot(page, "393-dark-link-prompt-4way.png")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("4-way linked 1 dimmer + 2 companions", q.get("Smart dimmer")==1 and q.get("Companion")==2, q)
        body = await page.inner_text("body")
        check("4-way summary still has group badge", "4-way (3 locations)" in body)
        await shot(page, "393-dark-four-way-linked.png")
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(150)
        body = await page.inner_text("body")
        check("4-way walk position badges", "4-way 1/3" in body and "4-way 2/3" in body and "4-way 3/3" in body)
        check("4-way walk has no N locations badge", "4-way (3 locations)" not in body)
        await shot(page, "393-dark-four-way-walk.png")
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(80)
        await shot(page, "393-light-four-way-walk.png")
        await page.emulate_media(color_scheme="dark")
        # Unlink the last (Foyer) switch; remaining two become 3-way 1/2 and 2/2
        unlinks = page.locator("[data-unlink]")
        check("4-way has three unlink buttons", await unlinks.count() == 3, await unlinks.count())
        await unlinks.nth(2).click()
        await page.wait_for_timeout(200)
        body = await page.inner_text("body")
        check("after unlink, remaining are 3-way 1/2 and 2/2", "3-way 1/2" in body and "3-way 2/2" in body)
        check("after unlink, 4-way position badges are gone", "4-way 1/3" not in body and "4-way 2/3" not in body and "4-way 3/3" not in body)
        # The unlinked third item should have no way badge in its list row
        labels = await page.eval_on_selector_all(".list-item", "els => els.map(el => el.innerText)")
        singles = [x for x in labels if x.strip().startswith("3.")]
        check("unlinked third switch has no way badge",
              singles and "3-way" not in singles[0] and "4-way" not in singles[0], singles)
        # Delete one of the remaining grouped switches (the first)
        await page.locator("[data-edit]").filter(has_text="1.").first.click()
        await page.wait_for_timeout(100)
        def _accept(dialog):
            asyncio.create_task(dialog.accept())
        page.on("dialog", _accept)
        await page.click("#deleteSw")
        await page.wait_for_timeout(200)
        page.remove_listener("dialog", _accept)
        body = await page.inner_text("body")
        check("after delete, leftover group member has no badge",
              "3-way 1/2" not in body and "3-way 2/2" not in body and "4-way 1/3" not in body)

        # Declared 4-way only
        await goto_walk_new_home(page, "Declared four way")
        await pick_room_load(page, "Kitchen", "Can lights")
        await page.click("#saveSw")
        await page.wait_for_timeout(200)
        await set_other_spots(page, 2)
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(100)
        await page.wait_for_timeout(200)
        await page.click("[data-tab='summary']")
        await page.wait_for_timeout(200)
        q = await qty_on(page)
        check("declared 4-way 1 dimmer + 2 companions", q.get("Smart dimmer")==1 and q.get("Companion")==2, q)
        check("declared 4-way summary badge", "4-way (3 locations)" in (await page.inner_text("body")))
        await shot(page, "393-dark-declared-four-way.png")
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(100)
        check("declared 4-way walk position badge", "4-way 1/3" in (await page.inner_text("body")) and "4-way (3 locations)" not in (await page.inner_text("body")))

        # Light + widths
        await page.emulate_media(color_scheme="light")
        await page.set_viewport_size({"width": 393, "height": 852})
        await page.wait_for_timeout(80)
        bg = await page.eval_on_selector("body", "el => getComputedStyle(el).backgroundColor")
        check("light bg", bg.replace(" ","") == "rgb(243,241,234)", bg)
        await shot(page, "393-light-summary.png")
        await page.click("[data-tab='walk']")
        await page.wait_for_timeout(80)
        check("light Which one? still absent", "Which one?" not in (await page.inner_text("body")))
        await shot(page, "393-light-walk.png")
        for w,h,label in ((840,820,"840-unfolded"), (1440,900,"1440-desktop")):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(80)
            await page.click("[data-tab='summary']")
            ov = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
            check(f"{label} light no overflow", ov)
            await shot(page, f"{label}-light-summary.png")
            await page.click("[data-tab='walk']")
            await shot(page, f"{label}-light-walk.png")
        await page.emulate_media(color_scheme="dark")
        for w,h,label in ((840,820,"840-unfolded"), (1440,900,"1440-desktop")):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(80)
            await page.click("[data-tab='summary']")
            ov = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
            check(f"{label} dark no overflow", ov)
            await shot(page, f"{label}-dark-summary.png")

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
        await page.reload(wait_until="load")
        await page.wait_for_selector("[data-tab='walk']", timeout=4000)
        check("reload after clear has no PIN screen",
              await page.locator("#keypad").count() == 0 and "Enter PIN" not in (await page.inner_text("body")) and "Set a PIN" not in (await page.inner_text("body")))
        await ctx.close()
        await browser.close()

    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    failed = [c for c in results["checks"] if not c["ok"]]
    print("\nSUMMARY", "PASS" if results["ok"] else f"FAIL {len(failed)}", "of", len(results["checks"]))
    sys.exit(0 if results["ok"] else 1)

asyncio.run(run())
