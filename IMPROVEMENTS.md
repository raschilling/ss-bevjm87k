# Switch Survey — improvements log

Dated entries for changes made on Tuesday, November 24, 2026 (America/New_York).

## 2026-11-24 — Fan type on the order (AC / DC / Not sure)

The Summary shopping list and CSV now follow fan type:

- **AC:** counted as a fan switch.
- **DC:** counted as an on/off switch (constant power), with a note that speed is via the fan remote or integration. Not counted as a fan switch.
- **Not sure:** listed in a **Verify on site** section and left out of buy counts until you choose.

## 2026-11-24 — Responsive layout

The app stays phone-first and now fits tablets, a foldable used folded (~344–360px) or unfolded (~700–840px), and desktop (1280 / 1440):

- Content is centered with a comfortable max width (~720px).
- Tap targets stay large.
- Inputs no longer stretch across a wide screen.
- Summary uses two columns on wider screens.

## 2026-11-24 — “Which one?” and plain-language hints

The old **Qualifier** label is now **Which one? (only if this room has two)**, with a short hint to skip it unless the room has two switches for the same kind of light (for example Left/Right recessed). The chips (Left, Right, Front, Back, Upper, Lower, 1–4) are unchanged. Visible “qualifier” wording was removed from the Summary, the CSV header (now **Which one**), and the instructions. The internal field key remains `qualifier` so existing saved data and imports still work.

Other jargon got short hints without extra taps: switch type, also controlled from, switches in this box, which slot, neutrals, and companions.

## 2026-11-24 — 3-way / 4-way visibility, “Also controlled from,” and linking

- Linked or declared multi-way switches show a **3-way** or **4-way** (N locations) badge in the walk list and on Summary.
- The link prompt says plainly: “Same light as …? This makes it a 3-way” (or 4-way when it is the third location).
- A 4-way (3 linked locations) orders **1 smart + 2 companions**.
- Optional **Also controlled from:** None / 1 other spot (3-way) / 2 other spots (4-way), default None. Useful when the other end has not been logged yet.
- Companion math is `max(declared extra spots, linked locations − 1)`, so logging and linking the other ends later does not double-count.
- The badge appears either way. The count is included in CSV/JSON (back-compatible).

## 2026-11-24 — PIN double-prompt fix

Unlock was sometimes asking for the PIN twice. Causes addressed:

- 4-digit auto-submit could fire a first attempt too early; every PIN now needs a tap on **OK**.
- The lock screen is clearly **Set a PIN** / **Confirm your new PIN** (first setup only) vs **Enter PIN** (unlock once).
- A stale “backgrounded” timestamp could re-lock immediately after a successful unlock. Background/foreground handling was tightened so a successful unlock stays unlocked.
- If the browser cannot persist `localStorage` (for example some private browsing modes), a visible warning is shown instead of silently falling back to setup.

Survey data is not stored on the server. If a PIN was never actually saved, set it once more; existing survey data in the same browser should still be there.

Safari and a home-screen web app are sometimes separate storage. Use one or the other consistently.

## 2026-11-24 — Switch type chips on the main form

**Dimmer / On/off / Fan** now sit on the main walk form (always visible, preselected from the Load, one tap to change). Choosing Fan reveals the AC / DC / Not sure chips. Gang size, slot, and the note stay under **More**.

## 2026-11-24 — Fixture quantity (“How many?”)

When Load is a multi-fixture type (can/wafer lights, sconces, pendants, under-cabinet, chandelier, flood, or exterior lights), an optional **How many?** row appears on the same screen (chips 1–8, plus **8+** with a number box). Stored as `fixtureCount`. The walk list uses a short form such as **Hall cans x6**. The count appears on Summary and in CSV/JSON. Older records without a count still work. If the count is 6 or more, Summary and the CSV add a reminder to check total fixture wattage against the switch’s rating.

## 2026-11-24 — Floor / room is the switch; light can be somewhere else

**Floor + Room = where the SWITCH is.** The form now says **Where the switch is**. An optional one-tap **Light is somewhere else** toggle reveals Light floor / Light room, defaulting to the switch’s floor and room. Stored as `lightFloor` / `lightRoom`. The order sheet and CSV show both only when they differ, for example `Switch: Main Stairs → Light: Main Kitchen`.

3-way linking and duplicate detection now key on the **light** (load + light location), not only the switch room, so a 3-way with switches in different rooms still links when both ends point at the same light. Named “Other” loads (for example Stair lights) still match across rooms by that name. Two different lights of the same type in different rooms on the same floor (Kitchen cans vs Hall cans) no longer auto-link unless you mark them as the same light. Older records without light fields are treated as “light is at the switch.”

## 2026-11-24 — Neutrals off the walk; automatic 3-way / 4-way

The **Neutrals in this house** card is gone from the walk screen. New homes default to **Most have a neutral**. Saved homes that were still **Not sure** / `unknown` are migrated to that default; explicit **Most do not** or **Mixed** are left alone. The example house also uses the default.

On **Summary**, next to Brand, there is a collapsed line: **Older house without neutrals? Change**. It opens the same choices. With the default, a short soft note says the app assumes boxes have a neutral (typical of homes built since the 1980s) and to flag a box with no white wire bundle. There is no longer an “open issue” nag for unknown/not sure.

Multi-way detection is automatic so you can walk every switch in order and not have to remember or declare 3-ways and 4-ways. **Also controlled from** (and the optional “where is this paddle”) moved under **More** — never a required walk step. Switches that control the same light (same load plus light location, including **Light is somewhere else**) are grouped as you save them, with a short “Linked as a 3-way/4-way with …” confirmation. There is no mid-walk prompt. The walk list is in logged order, with badges and an Unlink button on grouped items. Summary lists the detected groups with Unlink, **Ungroup all**, and **Merge with…**. Companion counts still do not double-count. Unlinking remembers the split so the same pair is not auto-grouped again until you merge them.

## 2026-11-24 — “Is the light in this room?”

The old **Light is somewhere else** toggle was confusing. It is now a plain yes/no question: **Is the light in this room?** Default is **Yes**, already selected, so no tap is needed when the light is with the switch. **No** reveals **Where is the light?** with floor and room. The stored keys are still `lightFloor` / `lightRoom`, so existing data and imports keep working. 3-way linking still keys on the light, including lights in another room.

## 2026-11-24 — Light location under More; Same light vs New light

**Light is in a different room** is now an optional choice under **More**, defaulting to the same room as the switch. It is not on the main walk screen, and there is no yes/no question there. Floor and room for the light still store as `lightFloor` / `lightRoom`.

When a new switch’s load and light location match a light already logged in that room, the app no longer auto-merges silently. It asks, in one tap, **Same light as &lt;name&gt;** or **New light**. Same light makes a 3-way or 4-way with that named light. New light asks for a short optional tag — Island, Sink, Front, Back, Left, Right, or auto **#2** / **#3** / **#4** — so the names stay distinct and the lights never merge. **Which one?** chips include those tags, and list names show them (for example Kitchen island cans). A switch you mark under More as controlling a light in another room still auto-groups with that light.

A “Not sure” fan now counts toward wallplates, because it still occupies a box. Pure regular (not smart) switches still do not appear on the order list.

## 2026-11-24 — End-to-end scenario suite

`verify_scenarios.py` walks 12 realistic houses in WebKit at 393px and asserts a hand-computed order sheet for each (dimmers, on/off, fan, companions, regular switches, wallplates, verify-on-site, and shopping-list / CSV / JSON agreement).

## 2026-11-24 — Tap a logged light’s name instead of “Light is in a different room”

The **More** choice **Light is in a different room**, and the floor/room fields for the light, are gone from the walk. To add another switch for a light already logged in this home, even from a different room or floor, tap its name under **Load**. Chips list unique lights already logged (load + tag + first room, for example **Upper Hall cans** or **Kitchen island cans**), most recent first, and they filter as you type. Tapping a name means “same light as that one” and groups the switch into a 3-way or 4-way, regardless of the switch’s room. Tapping the same chip again clears the pick.

Same-room **Same light** vs **New light**, plus the optional tags, is unchanged when you save a matching load without tapping a name. Existing `lightFloor` / `lightRoom` values are still stored and still used for labels, previews, and imports.

`verify_scenarios.py` S2 (stairs across floors) and S4 (4-way hall across rooms) now use the chip instead of the old More control.

## 2026-11-24 — Not sure if dimmable

When you don’t know whether the lights will dim, but still need to pick a switch, tap **Not sure if dimmable** next to Dimmer / On/off / Fan. There is no extra screen. It still orders a **dimmer** (counted with the other dimmers on the shopping list). The order sheet, CSV, and JSON include this note:

> Not sure if dimmable: set to on/off mode if the bulbs don't dim, or swap to dimmable LEDs.

Summary also shows a count, for example **3 dimmers marked not-sure-dimmable**.

Brand notes stay accurate against the manufacturer docs: Inovelli Blue and Red dimmers have a documented on/off mode. Caseta in-wall dimmers do not (only the plug-in lamp dimmer can convert to switch mode). If the bulbs don’t dim, leave a Caseta in-wall dimmer at full brightness, or swap to dimmable LEDs or a Caseta on/off switch. Lutron rates the in-wall dimmer for dimmable lamps only.

`verify_scenarios.py` S13 walks one regular dimmer, three not-sure dimmers, and one closet on/off, and asserts the order sheet, the exact note, the brand wording, and CSV/JSON.

## 2026-11-24 — Floor-specific rooms, Survey tab, hidden hints, fixture count

**Exterior** and **Basement** are no longer rooms. They are only floors, and the room list follows the floor you pick. Interior floors use the indoor rooms, A–Z. The Exterior floor shows outdoor spots, A–Z: Back patio, Deck, Driveway, Front porch, Garage exterior, Landscape, Side door, and Other. Basement adds **Main area** and **Utility** to the indoor list. Rooms stay the switch location.

Saved surveys are migrated: a room named Exterior becomes a sensible outdoor spot (or Other) on the Exterior floor; a room named Basement becomes **Main area** on the Basement floor. The example house now logs driveway floods and landscape lights under Exterior. Labels and the order sheet use `locPair` so a floor is not repeated in the name (no “Exterior Exterior”). Light-name chips still include the floor when it isn’t already in the room name, for example **Exterior Front porch floods** or **Garage exterior floods**.

The **Walk** tab and other user-facing “walk” wording are now **Survey** (the tab key is unchanged). The saved-switch list is **Survey order**.

Hint and description paragraphs are no longer always on screen. A small **i** icon next to the label reveals the text; it starts closed. Only the essential one-line labels stay visible. The same pattern is used on Summary. Spacing on the survey form is tighter so a full entry (floor, room, load, type, Save) fits on a 393×852 phone: Save is on screen without scrolling; about 86px of overflow is the Clear row below.

**How many?** is gone from the main form. For multi-fixture loads, a small **+ fixture count** control opens an optional **Fixtures on this switch** row (for example 6 cans). The stored key is still `fixtureCount`. It does not change what is ordered. The order sheet uses it only for the wattage-limit warning at high counts (6 or more) and, when the brand is Inovelli and the house has no neutrals, a flicker/bypass note for 1–2 small LEDs. S8 uses this collapsed control.

## 2026-11-24 — Remove “Which one?” from the form

**Which one? (only if this room has two)** is gone from the survey form. Same-type lights in the same room are handled only by the **Same light as X / New light** prompt and its tag chips (Island, Sink, Front, Back, Left, Right, #2 / #3 / #4). The stored key is still `qualifier`, so older surveys keep their tags in names, chips, and export. The CSV column is now **Tag**. S5 tags lights from that prompt (first cans, then Sink, then #2). Removing the field also lets a full entry, including Clear for next, fit on a 393×852 phone with no overflow (Save stays on screen).

Other form wording that was easy to trip over was simplified in the same pass:

- **Load** is now **What it controls** (the Other name field is **Name for what it controls**). Validation says “Choose what it controls.”
- Under More, **Where is this switch?** was easy to confuse with **Where the switch is** (floor and room). It is now **Doorway or wall, optional**, with **Custom spot** when you pick Other.
- The note placeholder no longer says “Traveler colors.” It is “Anything to remember at this box.”
- Light chips on the form are labeled **Lights already logged**.

## 2026-11-24 — No PIN; plain localStorage

The PIN setup, unlock, idle lock, and PIN settings are gone. New and already-plain surveys are saved in this browser as unencrypted JSON under `switchSurvey.data.v2`.

If a phone still has the older encrypted PIN copy (`switchSurvey.meta.v1`), the first open shows a one-time **Open your saved survey** prompt. Enter the old PIN once, the survey is decrypted and saved in plain form, and the encrypted copy is deleted. It will not ask again. A wrong PIN leaves the locked survey in place. If the old PIN is unknown, starting fresh erases only that locked copy (a JSON backup can still be imported).

S11 and the other reload checks now confirm the survey comes back with no unlock step. `verify_plain_storage.py` seeds an encrypted home, unlocks it once, and asserts the homes, switches, and JSON export are kept, then that a second reload stays unlocked.

CSV/JSON import and export, noindex, and robots.txt are unchanged.
