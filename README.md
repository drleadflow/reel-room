# Reel Room


Type `/reel` in Claude Code, give it your talking-head clips, and get a finished 9:16 reel: best takes picked, dead air and false starts cut in real silence, captions that match what you said, graphics that land on the word, and files ready to post (master, share copy, silent version, captions, cover).

This is the full version: eight looks, the Room (a private review page for storyboard, snips, colour, hook, cover and caption), the graphics kit and hero library, the vision judge and the number check.

## Quick start (about 3 minutes of your time)

You need: macOS, Linux or Windows 10/11, [Claude Code](https://claude.com/claude-code), about 4 GB free disk plus 2 to 5 GB per reel while it renders. Tested on macOS (Apple Silicon); Linux and Windows installers are included but not yet tested. The installer finds or installs Python 3.12, ffmpeg and Node 22 (it asks first).

```bash
git clone <this repo's URL> reel-room && cd reel-room
./install.sh          # Windows: powershell -ExecutionPolicy Bypass -File .\install.ps1
./reel setup          # your name, handle, colours (Enter keeps the defaults)
./reel demo your-clip.mov   # your own 20 to 60 s vertical clip -> a finished reel
```

No clip yet? Record 20 to 60 seconds of yourself talking about one idea, phone held upright (any phone is fine), and copy it to your computer. `./reel demo` with no clip prints these steps. The demo checks the clip first (vertical, 15 to 120 s, has sound, one face) and tells you in plain words if something is off.

`./reel demo` takes about 4 minutes for a 45 s clip (Split deck) and about 9 minutes with `--style editorial-ui` (the cut-out runs first) on a laptop with the CPU cap on. The demo makes a quick first-pass edit from your words; `/reel` in Claude Code does the full job (best takes picked by ear, a plan written for your reel, notes and rounds).

The install downloads about 3 GB once (speech models 1.9 GB, the video engine and its Chrome 0.8 GB, Python packages 0.35 GB, the cut-out model 0.18 GB) and took 7 minutes on a fast connection in testing (longer on slower Wi-Fi; you can walk away). Then open Claude Code anywhere and type `/reel`, followed by the path to your clip (drag the file into the chat box).

## Try these first

- `./reel try` prints 10 starter requests. The full list of phrases, grouped by what they do, is in [PHRASES.md](PHRASES.md).
- The previews below show what each phrase does. Say the phrase in Claude Code while `/reel` is open on a reel.

### Styles

<table>
<tr><td align="center" valign="top"><img src="skills/reel/styles/previews/split-deck.gif" width="180" alt="Cards on the top half, you on the bottom half, short captions on the seam"><br><code>Edit this in Split deck</code><br><sub>Cards on the top half, you on the bottom half, short captions on the seam</sub></td><td align="center" valign="top"><img src="skills/reel/styles/previews/editorial-ui.gif" width="180" alt="You, cut out onto a solid colour set that changes on every beat, with huge serif words behind your head"><br><code>Edit this in Editorial UI</code><br><sub>You, cut out onto a solid colour set that changes on every beat, with huge serif words behind your head</sub></td><td align="center" valign="top"><img src="skills/reel/styles/previews/motion-editorial.gif" width="180" alt="Animated graphics fill the top half (kinetic words, a circled number, a lab sheet, a gauge, a calendar) and you sit in a rounded card below"><br><code>Edit this in Motion editorial</code><br><sub>Animated graphics fill the top half (kinetic words, a circled number, a lab sheet, a gauge, a calendar) and you sit in a rounded card below</sub></td><td align="center" valign="top"><img src="skills/reel/styles/previews/clean-talk.gif" width="180" alt="You, full frame and natural"><br><code>Edit this in Clean Talk</code><br><sub>You, full frame and natural</sub></td></tr>
<tr><td align="center" valign="top"><img src="skills/reel/styles/previews/list-stack.gif" width="180" alt="A numbered list builds above your head as you say each item"><br><code>Edit this in List stack</code><br><sub>A numbered list builds above your head as you say each item</sub></td><td align="center" valign="top"><img src="skills/reel/styles/previews/floating-cards.gif" width="180" alt="Small frosted cards pop in around you on the exact word, plus one big word behind your head"><br><code>Edit this in Floating cards</code><br><sub>Small frosted cards pop in around you on the exact word, plus one big word behind your head</sub></td><td align="center" valign="top"><img src="skills/reel/styles/previews/carousel-slideup.gif" width="180" alt="One cream card per point slides up over the lower half on each cut, like swiping a carousel"><br><code>Edit this in Carousel slide-up</code><br><sub>One cream card per point slides up over the lower half on each cut, like swiping a carousel</sub></td><td align="center" valign="top"><img src="skills/reel/styles/previews/desk-demo.gif" width="180" alt="Cuts from you to a phone-filmed screen (a lab portal, an app, a calendar) where a cursor clicks and highlights what you're talking about"><br><code>Edit this in Desk demo</code><br><sub>Cuts from you to a phone-filmed screen (a lab portal, an app, a calendar) where a cursor clicks and highlights what you're talking about</sub></td></tr>
</table>

### Graphics and hero moments

<table>
<tr><td align="center" valign="top"><img src="docs/previews/kit-typer.gif" width="180" alt="typer"><br><code>Type it like a prompt</code><br><sub>typer</sub></td><td align="center" valign="top"><img src="docs/previews/kit-checklist-tick.gif" width="180" alt="checklist tick"><br><code>Tick them off as I say them</code><br><sub>checklist tick</sub></td><td align="center" valign="top"><img src="docs/previews/kit-odometer.gif" width="180" alt="odometer"><br><code>Count it up</code><br><sub>odometer</sub></td><td align="center" valign="top"><img src="docs/previews/kit-label-pill.gif" width="180" alt="label pill"><br><code>Strike "{word}" out</code><br><sub>label pill</sub></td></tr>
<tr><td align="center" valign="top"><img src="docs/previews/kit-receipt.gif" width="180" alt="receipt"><br><code>Show the cost adding up</code><br><sub>receipt</sub></td><td align="center" valign="top"><img src="docs/previews/kit-before-after.gif" width="180" alt="before after"><br><code>Show a before and after</code><br><sub>before after</sub></td><td align="center" valign="top"><img src="docs/previews/hero-money-counter.gif" width="180" alt="money counter"><br><code>Add a money counter on 60 billion</code><br><sub>money counter</sub></td><td align="center" valign="top"><img src="docs/previews/hero-fire-timeline.gif" width="180" alt="fire timeline"><br><code>Put a fire timeline on cooked</code><br><sub>fire timeline</sub></td></tr>
<tr><td align="center" valign="top"><img src="docs/previews/hero-title-stamp.gif" width="180" alt="title stamp"><br><code>Stamp it as a big headline</code><br><sub>title stamp</sub></td><td align="center" valign="top"><img src="docs/previews/hero-word-stamp.gif" width="180" alt="word stamp"><br><code>Stamp "cooked" huge</code><br><sub>word stamp</sub></td><td align="center" valign="top"><img src="docs/previews/hero-cycle-chart.gif" width="180" alt="cycle chart"><br><code>Draw the drop on a chart</code><br><sub>cycle chart</sub></td><td align="center" valign="top"><img src="docs/previews/hero-nle-timeline.gif" width="180" alt="nle timeline"><br><code>Show the editing timeline of this video</code><br><sub>nle timeline</sub></td></tr>
</table>

<sub>What you'll get: these previews are the author's own reels, used with permission.</sub>

## How to talk to it

- Give it the clip path, say what the reel is for, pick a style. It shows you the plan as a short list before it renders.
- Ask for changes in plain words, on one moment: "make this part simpler", "add a whip here", "count it up on 65 degrees", "let this breathe". See [PHRASES.md](PHRASES.md).
- It never cuts or softens what you say without asking, and it flags medical numbers or promises once.
- Nothing is posted anywhere unless you say yes in chat.

## Keys and costs

`OPENROUTER_API_KEY` is recommended (https://openrouter.ai/keys): fast planning (about 20 s, about $0.03 to $0.05 per reel), model picks per beat and hero, the number check's model verdict, the vision judge (about $0.005 per clip, $0.04 with `--strong`) and analyze_refs. Without it Claude Code plans and the judge is off. `GEMINI_API_KEY` (free, https://aistudio.google.com/apikey) turns on the AI style scan. `ZERNIO_API_KEY` turns on automatic posting. `./reel doctor` lists exactly what each missing key turns off.

Keys live in `.env` (copy `.env.example`) or your environment, nothing else. `.env` is git-ignored. Speech recognition, rendering and QA run on your computer for free.

## Commands

| Command | What it does |
|---|---|
| `./reel doctor` | Checks every dependency and key; prints the exact fix for each problem on your OS |
| `./reel setup` | Brand wizard: name, handle, colours, fonts, call to action, folders |
| `./reel demo <clip> [--style editorial-ui]` | Your clip -> a finished reel (no clip: prints how to record one) |
| `./reel try` | Prints 10 starter requests |
| `./reel assets` | Re-downloads models and the video engine (resumes) |
| `./reel run engine/<script>.py ...` | Runs an engine script with your `.env` keys loaded |

Windows: use `.\reel.cmd` instead of `./reel`.

## Safe on a laptop

- CPU cap: every heavy step uses about half your cores (`RR_MAX_THREADS`, set it in your environment to change), runs at low priority (nice 10), and only one heavy job runs at a time.
- It warns when free disk is under 10 GB. A reel uses 2 to 5 GB while it renders; finished projects live in `projectsDir` (default `~/ReelRoom`).
- Your clips are never moved, renamed or deleted.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Anything at all | `./reel doctor`, then run the fix it prints under each FAIL line |
| `/reel` does nothing in Claude Code | `./install.sh --skill-only`, then restart Claude Code |
| A download stopped halfway | Run `./install.sh` again (downloads resume) |
| `node` too old | macOS `brew install node@22`; Linux NodeSource 22; Windows `winget install OpenJS.NodeJS.LTS` |
| Render fails with a Chrome error | `npx --yes hyperframes@0.8.34 browser ensure` |
| A word is misspelled in the captions | Tell Claude: `Fix the caption: "wrong" should be "right"` |
| A number disappeared from the captions | The number check could not confirm it; Claude asks you to confirm it |
| The laptop is slow while rendering | Expected; lower the cap with `RR_MAX_THREADS=2` |

## Known limits

- `reel demo` is a quick first pass: it keeps every phrase you said (it drops pauses and an obvious retake) and plans from your words with simple rules. For take picking, a written plan and notes, use `/reel`.
- Tested on macOS (Apple Silicon, 2 machines). The Linux and Windows installers are written but not yet tested.
- Planned engine fix after this release: a sanity cap on the face box the QA face detector returns.

## Updating

`git pull`, then `./install.sh` (it only installs what changed).

## Licence

MIT licensed: see [LICENSE](LICENSE). Use it, change it, redistribute it, make it your own. Third-party credits: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
