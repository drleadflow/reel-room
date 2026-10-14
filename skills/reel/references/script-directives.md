# Script directions

Creators often write their edit notes into the script: "(make this full screen)", "(big text)", a gif link, a number
pointing at a photo. When a script exists, those notes drive the storyboard first. Claude fills only the beats the
creator left open.

## Where the script lives

`P/script.md` or `P/script.txt` (or any file: `script.py P --script FILE`). Plain text or Markdown. Ask for it at
ingest: "Do you have the script, with any notes on what should be on screen?" A pasted script goes into `P/script.md`
as is. Headings (`# ...`) are ignored, `**bold**` is ignored.

## Grammar

A direction is any text in `( )` or `[ ]`, or a bare link. It covers the words just before it: back to the previous
direction or the start of the sentence, whichever is closer. Two directions in a row share the same words. A direction
with no words before it (start of the script) covers the next sentence.

To point at exact words, highlight them: `==fasting insulin==`. When the stretch has highlighted words, the direction
covers only those (first to last highlight).

| Write | Means | `directive` |
|---|---|---|
| `(full)` `(full screen)` `(make full screen)` | the visual fills the frame for this line | `full` |
| `(big text)` `(big, bold text)` `(bold text)` | a typography moment: the key words big, connecting words small. Never a copy of the captions | `big_text` |
| `(split)` `(half screen)` | visual on top, speaker below | `split` |
| `(card: 2)` `(card: assets/x.png)` | one proof or screenshot card | `card` |
| `(pop each as I say, hold until "Meta")` | pop items in one by one on their words, keep them all up until that word ends | `pop` (`each`, `until_word`, `until_t`) |
| `(list)` | this line is a list item: use the list scaffold | `list` |
| `(presenter)` `(just me)` `(no graphics)` | speaker only, no visual. A valid choice | `presenter` |
| `(gif: <url>)` or a bare giphy / tenor / .gif link | reaction gif. Stored as a link only | `gif` |
| `(broll: hands typing on a laptop)` | B-roll to find or shoot. Describe it, Claude never invents it | `broll` |
| `(show: lab report)` | a visual of this thing | `show` |
| `(1)` `(2)` | asset number N: the file in `P/assets/script/`, `P/assets/` or `P/assets/broll/` whose name starts with N (`1-amazon.jpg`, `02_meta.png`) | `asset` |
| `(1 - make full screen)` | a number plus a direction: asset 1, shown full screen | `full` + `asset:1` |
| any other link | saved, never fetched | `link` |

Anything else is kept as written with `directive: "unknown"` and a flag. Short ones like `(files)` get a guess
("show files?"). Never drop or rewrite a direction you cannot read. Ask.

## Run it

```
PY SK/engine/script.py P            # -> P/work/directives.json, prints one line per direction and every flag
```

Before assemble the times come from `edl.json` plus the source words (close, not exact). After assemble they come from
`words.json`. Re-run after assemble or after any snip round.

`work/directives.json`:
```json
{"script": ".../script.md", "timing": "words.json", "flags": 2, "items": [
  {"n": 3, "t0": 6.4, "t1": 12.1, "seg": "cred2", "line": "I also was a health coach ...", "directive": "full",
   "args": {"asset": 1, "src": "assets/1-coaching.jpg"}, "raw": "1 - make full screen",
   "suggest": {"layout": "full-visual", "insert": "image", "src": "assets/1-coaching.jpg"}}]}
```
`t0`/`t1` are cut-time seconds, `null` when the line is not in the cut. `suggest` is style neutral: map it to the
chosen style's own inserts (split-deck names in `inserts.md`).

## Turning directions into beats

1. Every direction with times becomes a beat (or part of one) at `t0`. Keep `raw` in the beat's `flag` only when it is
   flagged. Set `purpose` yourself (`inserts.md`).
2. The rest of the reel: Claude plans the beats with the usual rules.
3. If the style cannot do a direction (for example a full-screen image in a split-only look), pick the closest thing it
   can do and say so in the beat's `flag`, in one plain sentence.
4. Flags to the storyboard, in plain words: missing asset ("asset 2 is not in the folder yet"), line not in the cut,
   unknown direction, gif links waiting for a yes.
5. Gif and web links: never download until the user says yes in chat. Then save the file into `P/assets/script/`.
6. The direction never changes what the creator says. It changes only what is on screen.
