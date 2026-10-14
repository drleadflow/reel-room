# Brand setup (first run)

Run this once, when `~/.reel-room/brand.json` does not exist. Ask in plain words, one short block, not one question at a time. Offer a default for each so the user can answer "ok" to everything.

## Questions

1. Your name as it should appear (name on cards and the CTA). Example: Your Name.
2. Your Instagram handle, without the @.
3. Colours. Ask for a brand color to use as the accent. If they have none: offer green `#1B8A68`, red `#C8323F`, blue `#2457D6`. Derive the rest:
   - `bg` light paper `#F4F1EC`
   - `ink` near black `#0C0C0F`
   - `accent` their color
   - `accent2` a pale tint of the accent (used for line 2 on hook cards)
   - `highlight` soft yellow `#FAE67A`
   - `alert` red `#C8323F` (used for results on polaroids)
4. Fonts. Defaults: Inter Tight (display), Inter (body), Caveat (hand). All are OFL fonts, the template embeds them. Only change if they name another OFL font.
5. Call to action. Keyword (one short word, for comment-to-DM) and the line, like "Comment AGENT". Or "none".
6. Logo (optional). A file path to a PNG with transparency. Copy it into `~/.reel-room/logo.png`, set `logo` to that path.
7. Folders. Where finished projects go (`projectsDir`) and where new clips usually land (`clipsDir`). Defaults: `~/ReelRoom` and `~/Downloads`.
8. Voice notes (optional). One or two lines on how you sound: for example "direct, short sentences, dry humor, no hype". Used to grade captions. Store as `voice`, or leave it out.

## Schema: `~/.reel-room/brand.json`

```json
{
  "name": "Your Name",
  "handle": "yourhandle",
  "colors": {
    "bg": "#F4F1EC",
    "ink": "#0C0C0F",
    "accent": "#1B8A68",
    "accent2": "#E2F5EA",
    "highlight": "#FAE67A",
    "alert": "#C8323F"
  },
  "fonts": { "display": "Inter Tight", "body": "Inter", "hand": "Caveat" },
  "cta": { "keyword": "AGENT", "text": "Comment AGENT" },
  "logo": null,
  "projectsDir": "~/ReelRoom",
  "clipsDir": "~/Downloads"
}
```

Rules:

- All colors are 6-digit hex strings. Check contrast: `accent2` text must be readable on `accent`, and white must be readable on `accent`. If not, pick a darker accent and say so.
- `cta` may be `null` if the user wants no CTA. Then templates drop the CTA card.
- `logo` is an absolute path or null.
- `voice` is an optional string. If missing, the caption grader scores voice match as neutral.
- `lessons` is an optional list of one-line lessons from the user's feedback (`["Hold the face after a number card",
  "No gifs"]`). Claude reads them at setup and appends one after feedback that applies to future reels. Keep the last 30.
- Store `~` paths expanded when you use them. Keep the file readable by hand.
- Per-project override: a `brand` block in `project.json` merges over this file for that reel only.
- Never put secrets in `brand.json`.

After writing, print the file back as a short block and ask: "Good, or change anything?"
