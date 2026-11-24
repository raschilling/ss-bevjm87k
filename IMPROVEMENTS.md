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
