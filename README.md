# Switch Survey

Private, phone-first survey for ordering smart switches. Single-file app. No login. Data stays on the phone, in this browser.

## Open it

1. Copy `index.html` to your phone (AirDrop, Messages, or a private unlisted HTTPS link).
2. Open it in Safari. Share → Add to Home Screen. The home-screen name is **Switch Survey**.
3. Name the home, then survey switches. Floor and room stick after you save. Changes autosave in this browser.

Safari is required for reliable save. Chrome or a Files preview may evict data.

If this phone already has a survey that was locked, you will be asked for the old PIN once. After that, the survey is saved in plain form on this phone and will not ask again.

## Features

- Multiple homes, separate exports
- System light/dark (follows the phone)
- Export JSON backup, CSV order sheet, and Copy/Share of the data (not just the page URL)
- Import JSON
- Example house on the Homes tab

## Hosting

This folder is a local copy only. It is not published. Prefer an unlisted HTTPS URL with noindex, a random path, and no public repo listing. Cloudflare Pages, Netlify, or a host you already control can do that. GitHub Pages on a public repo is a poor fit. Home Assistant `/local/` usually still requires HA login and was not writable from here.
