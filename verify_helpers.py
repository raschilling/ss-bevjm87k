"""Shared Playwright helpers for Switch Survey tests."""
import re

async def choose_load(page, load):
    sel = page.locator("#loadType")
    if await sel.count():
        await sel.select_option(load)
        await page.wait_for_timeout(80)
        return
    inp = page.locator("#loadQuery")
    await inp.click()
    await inp.fill(load)
    await page.wait_for_timeout(60)
    await inp.press("Enter")
    await page.wait_for_timeout(80)

async def pick_existing_light(page, contains):
    # iOS can deliver a leftover tap onto a newly rendered chip; the app ignores those briefly.
    await page.wait_for_timeout(500)
    chips = page.locator("[data-pick-light]")
    visible = False
    if await chips.count():
        for i in range(await chips.count()):
            if await chips.nth(i).is_visible():
                visible = True
                break
    if not visible:
        inp = page.locator("#loadQuery")
        await inp.click()
        await page.wait_for_timeout(80)
    await page.wait_for_selector("[data-pick-light]", state="visible", timeout=4000)
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
    raise AssertionError(f"no visible light suggestion containing {contains!r}; chips={labels}")

async def open_more(page):
    more = page.locator("#more")
    if await more.count() and "hidden" in ((await more.get_attribute("class")) or "").split():
        await page.click("#moreToggle")
        await page.wait_for_timeout(80)

async def set_other_spots(page, n):
    """Seed declared otherSpots on the most recently saved switch (UI control removed)."""
    await page.evaluate(
        """(n) => {
          const key = "switchSurvey.data.v2";
          const data = JSON.parse(localStorage.getItem(key) || "null");
          if (!data || !data.store) return false;
          const home = (data.store.homes || []).find((h) => h.id === data.store.activeHomeId) || (data.store.homes || [])[0];
          if (!home || !home.switches || !home.switches.length) return false;
          home.switches[home.switches.length - 1].otherSpots = n;
          localStorage.setItem(key, JSON.stringify(data));
          return true;
        }""",
        n,
    )
    await page.reload(wait_until="load")
    await page.wait_for_selector("[data-tab='walk']", timeout=8000)
    await page.wait_for_timeout(100)

async def show_parts(page):
    btn = page.locator("#toggleParts")
    if await btn.count() and (await btn.get_attribute("aria-expanded")) != "true":
        await btn.click()
        await page.wait_for_timeout(100)


async def set_light_place(page, room, floor=None):
    """Set the Light is in dropdown. room is 'same', 'Other', a room name, or a 'Floor|Room' value."""
    sel = page.locator("#lightPlace")
    await sel.wait_for(state="visible")
    if room in ("same", "", None, "Same"):
        await sel.select_option("same")
    elif room == "Other":
        await sel.select_option("Other")
    elif "|" in room:
        await sel.select_option(room)
    else:
        await sel.select_option((floor or "Main") + "|" + room)
    await page.wait_for_timeout(80)
