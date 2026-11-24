"""Shared Playwright helpers for Switch Survey tests."""
import re

async def choose_load(page, load):
    inp = page.locator("#loadQuery")
    await inp.click()
    await inp.fill(load)
    await page.wait_for_timeout(60)
    item = page.locator(f'[data-pick-load="{load}"]')
    if await item.count():
        await item.first.click()
    else:
        await inp.press("Enter")
    await page.wait_for_timeout(80)
    if await page.locator("#loadSuggest:not(.hidden)").count():
        await page.locator("h1").click()
        await page.wait_for_timeout(80)

async def pick_existing_light(page, contains):
    inp = page.locator("#loadQuery")
    await inp.click()
    await page.wait_for_timeout(80)
    await page.wait_for_selector("#loadSuggest:not(.hidden) [data-pick-light]", timeout=4000)
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
