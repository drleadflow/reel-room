# Styles

The Styles tab reads `styles/catalog.json`. That file is the source of truth for ids, names, templates and previews (`styles/previews/<id>.gif`, the same sample clip edited 8 ways). If the user picks nothing, build `split-deck`.

## On real reels (showcase)

`catalog.json` styles can carry `examples` (finished concept-demo reels re-cut in that style) and the top level
`examples_offcatalog` (a look the catalog does not have, with `style_label`). Files: `styles/showcase/<reel>-<style>.mp4`
+ `.jpg`. The Styles tab shows them as an "On real reels" row under each card (tap: muted player with a "Concept demo"
note) and a "Same reel, two styles" compare. Publishing them: room-protocol.md "Showcase examples". They are demos of
real people for the owner's own Room only, never shown elsewhere without that person's OK.

## Catalog ids

| id | Family | Needs cutout | What it is |
|---|---|---|---|
| `editorial-ui` | cutout | yes | Speaker cut out onto solid colour sets that change per beat, huge serif words behind the head, cuts back to the room for prompt bars, checklists, a countdown. |
| `clean-talk` | overlay | no | Full frame and natural. One white caption word at chest height, a small 3-line title, one or two gold keywords, a couple of small cards. |
| `motion-editorial` | split | no | Animated graphics fill the top half (kinetic words, a circled number, a lab sheet, a gauge), speaker in a rounded card below. |
| `split-deck` | split | no | **Default.** Cards and B-roll on top, speaker below, short captions on the seam, hook card, checklists that tick. |
| `list-stack` | overlay | no | A numbered list builds above the head as each item is said, the current item lights up. For "5 things" reels. |
| `floating-cards` | overlay | yes | Small frosted cards pop in around the speaker on the exact word, one big word behind the head, one caption word at a time. |
| `carousel-slideup` | carousel | no | One cream card per point slides up over the lower half on each cut, static title on top, no captions. |
| `desk-demo` | screen | no | Cuts to a phone-filmed screen (portal, app, calendar) where a cursor clicks and highlights the point. |

Presets ride on a style: `"preset": "kallaway"` with `split-deck` (or no style) gives the split-held news-deck look
(top-slot picture about every 1.0 s from `assets/broll/`, topic banner, receipt-proof beat, one analogy full frame,
head bubble, comment CTA) with calm captions and light SFX. "Make it like Kallaway" maps to it. Details:
`templates/split/README.md` "Presets".

A style with `"coming": true` shows "Coming soon". If the user picks one, say so in one line and build `split-deck`.

## Style scan (beta): learn a style from reels

`engine/style_scan.py` (CLI) uses `style_pixels.py` (offline numbers) and `style_ai.py` (Gemini).

1. Inputs. `--files <3 to 5 videos or a folder>` is the reliable path: ask the user to save the reels and send the paths. Handles and links go through yt-dlp; Instagram blocks profile pages and often single reels too (`--cookies-from-browser chrome` helps sometimes). On failure the script prints the "save 3 to 5 reels" fix: relay it.
2. Modes. `--mode creator` = a creator they want to look like (the card describes "their system"). `--mode vibe` = their own reels ("your look").
3. AI path (key found): each reel is uploaded to the Gemini Files API, watched, deleted right after. Gemini answers a strict per-reel JSON (layout with time shares, captions, title, graphics, cutout, colour, pacing, sound, signature moves). A second text-only call aggregates: `summary`, `system` rows, `consistent`, `varies`, top 3 `matches` from the CURRENT catalog only (ids validated, unknown ids dropped, refilled from the pixel guess), `confidence`, `no_fit` (plain sentence when the best fit is under 55%). Models: gemini-3.7-flash, then 3.5-flash, then 3.5-flash-lite; busy (429/503) waits and retries, quota errors move on. About 2 to 2.5 minutes and 40k to 55k tokens for 5 reels (a few cents on flash pricing).
4. No key, or `--basic`: pixel numbers only, labelled "Basic scan (no AI key)", fits capped at 60%, confidence low, plus the free key setup line (`GEMINI_API_KEY=` in `~/.reel-room/.env` or the environment; `~/.config/watch/.env` is read too). Never print the key.
5. Output: `~/.reel-room/style_scans/<name>/style_card.json` (or `--out`) and `contact_sheet.jpg`. `--json` prints the card without the per-reel detail.

Writing it to the Room: upload `contact_sheet.jpg` as an asset and set `sheet` to its url, then `start/result {at, cards:[card], suggestions: card.recommended_styles}`. In chat, give the top pick and its reason in one line. If `no_fit` is set, say it plainly and suggest the closest one anyway. Never invent a style id; if the user asks for a look the catalog does not have, say so.

The matching hints Gemini sees live in `style_ai.py` `SIGNALS` (one line per id). A new catalog style without an entry falls back to its `desc`; add a line there when you add a style.
