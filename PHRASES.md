# Say this to get that: Reel Room

Type these in Claude Code while `/reel` is open on a reel. Plain words work; these are the phrases the
editor maps to exact engine actions. `{word}` means: put the word from your line there, for example
`Punch in on "billion"`. Say where ("here", "on the second point", "at 0:24") and only that moment
changes.

## Calmer

_Too much going on? Take it down._

| Say | What it does |
|---|---|
| `Make this part simpler` | Drops this beat one motion level (Showreel to Polished to Simple). |
| `Remove the graphics here` | Takes the card or graphic off this beat. Just you and the captions. |
| `Fewer zooms` | Holds the camera still on this beat. No punches or push-ins. |
| `Plain cut here, no transition` | The cut into this beat becomes a clean cut. |

## More motion

_Feels flat? Give it a hit._

| Say | What it does |
|---|---|
| `Add a whip here` | A fast whip pan with motion blur into this beat. |
| `Make the hook hit harder` | Opening beat goes Showreel: kinetic hook type, a punch on the payoff word, a sound on the hit. |
| `Punch in on "{word}"` | A quick zoom hit exactly on that word, then back. |
| `Show off on this part` | This beat goes Showreel: its own move on the cut, camera always moving, graphics land with weight. |

## Graphics

_One graphic, on one moment. Say it while the moment is fresh, or name the word._

| Say | What it does |
|---|---|
| `Big word behind my head on "{word}"` | A giant word sits behind you, your head in front of it. |
| `Type it like a prompt` | The line types out in a chat or prompt bar, letter by letter. [preview](docs/previews/kit-typer.gif) |
| `Tick them off as I say them` | A checklist where each item ticks on the word you say it. [preview](docs/previews/kit-checklist-tick.gif) |
| `Count it up` | The number rolls up like an odometer and lands on your word. [preview](docs/previews/kit-odometer.gif) |
| `Draw an arrow at it` | A hand-drawn arrow draws on and points at the thing you mean. |
| `Show a chart here` | A simple bar or line chart builds as you talk through the numbers. |
| `Show the chart from the study` | The study's chart builds on your words, the key number stamps in and the source stays on screen. |
| `Grade it moodier here` | Darker, more contrast on this part only. Skin stays natural. |
| `Shrink me into a phone` | You shrink into a phone screen and the app shows around you. |
| `Put the key word behind me` | Claude picks the strongest word in this line and puts it behind your head. |
| `Strike "{word}" out` | The word pops in as a label, gets crossed out and tumbles away. [preview](docs/previews/kit-label-pill.gif) |
| `Show the cost adding up` | A receipt stacks up line by line and lands on the total. [preview](docs/previews/kit-receipt.gif) |
| `Show a before and after` | A wipe slides from the before to the after. [preview](docs/previews/kit-before-after.gif) |
| `Spotlight this part` | Everything dims except the one thing you are talking about. |
| `Show the steps as I go` | A step counter moves to the step you are on. |
| `Fill a progress bar` | A bar fills up as you get closer to the point. |
| `End on the comment-for-DM` | A comment with your keyword appears and turns into a DM. |
| `Circle it` | A hand-drawn circle draws around the thing you mean. |

## Hero moments

_Premium, bespoke moments for the lines that matter most (a few per reel)._

| Say | What it does |
|---|---|
| `Stamp it as a big headline` | Your line becomes a huge serif headline stamped in on the word, with a colour change behind it. [preview](docs/previews/hero-title-stamp.gif) |
| `Roll the number up and step it` | The number rolls up, slams on your word, then steps to the next number you say. [preview](docs/previews/hero-money-counter.gif) |
| `Draw the drop on a chart` | A line draws on your words: it holds then plunges, or dips and recovers, with a stopwatch and a stamp. [preview](docs/previews/hero-cycle-chart.gif) |
| `Slam the study number in big` | The study's key number slams in, its chart builds and the source card lands. Needs the study. |
| `Show the editing timeline of this video` | A real editing timeline of this video builds on your words, a playhead races across, then it folds away. [preview](docs/previews/hero-nle-timeline.gif) |
| `Set the timeline on fire` | An editing timeline chars, catches fire on your word and drops away. [preview](docs/previews/hero-fire-timeline.gif) |
| `Stamp "{word}" huge` | One giant word stamps in letter by letter, behind your head when there is a cut-out. [preview](docs/previews/hero-word-stamp.gif) |
| `Fan out the styles like a paint deck` | Swatches fan out, each a little live preview, and the one you pick lifts out on your word. |
| `Show it as a video with chapters` | A video player card unfolds, plays on your word and skips through the chapters. |
| `Shrink me into a grid` | You shrink into the middle of a 3x3 grid of your own clips, then they fall away and you snap back. |
| `Make it a magazine cover` | The frame turns into a magazine cover: a masthead, coverlines beside you, a sticker. |
| `Orbit my reels around me` | Your own reels spin around you, some passing in front, some behind your head. |

## Timing

_Tighter, or room to breathe._

| Say | What it does |
|---|---|
| `Tighter` | Trims the small pauses in this beat. Words stay the same. |
| `Let this breathe` | Keeps a beat of silence after this line so it lands. |
| `Cut the pause before "{word}"` | Removes the gap right before that word. |
| `Stay on my face longer here` | The graphic comes in later so the face holds a moment first. |

## Captions

_What is on screen matches what you said, spelled your way._

| Say | What it does |
|---|---|
| `Just captions on this part` | Speaker full frame with plain captions. No cards, no camera moves. |
| `Fix the caption: "Ozempick" should be "Ozempic"` | Corrects that word everywhere it was misheard (words.py fix), kept on every rebuild. |
| `Spell my name and brand words right: <names>` | Saves them as spelling hints for the speech model before the transcript runs (names.txt). |
| `Keep the captions up through short pauses` | Holds a caption through a pause instead of blinking off (captions.hold_gap). |
| `Captions straight from what you heard, not my script` | Whisper-only captions (captions_from: whisper). |

## Sound

_Sound effects sit 20 to 22 dB under your voice. No music unless you ask._

| Say | What it does |
|---|---|
| `No sound effects` | Voice only. Every whoosh and pop is removed from the reel. |
| `More sound effects` | A sound on every transition and graphic, still under your voice. |
| `Make the sound effects lighter` | Light SFX: sparse, only on transitions and new graphics. |
