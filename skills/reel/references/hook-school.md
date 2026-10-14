# Hook school

The on-screen title is the first thing a viewer reads. It has one job.

## The goal sentence

**A title opens a question in the viewer's head that only the video can close.**

If the viewer reads it, nods and thinks "makes sense", it failed. A label tells them the topic. A hook withholds the payoff.

- Dead: WHY A DOCTOR / BUILT AN AGENCY (a topic label, rejected)
- Alive: THE SKILL DOCTORS / NEVER GET TAUGHT (you want to know the skill)

## Shape (every category)

- Exactly 2 lines.
- 2 to 4 words per line.
- ALL CAPS.
- The pull is in the first 3 words.
- Line 1 white. Line 2 takes the category colour.
- Holds about 3.6 seconds, then fades.
- The video answers it inside the first 5 seconds of speech.

## The six categories

Colours follow the owner's shipped convention (red warns, green optimises, blue reframes or asks, gold names a mechanism). Receipt, Callout and a few shades are Room additions so all six look different on the cards.

| Category | Colour | Use when | Example |
|---|---|---|---|
| Contrarian | red `#FF1A1A` | you disagree with common advice | DON'T START / WITH THE GYM |
| Receipt | orange `#FF8A1A` | you have a real number or result | I HIRED 4 / AI EMPLOYEES |
| Hidden mechanism | gold `#FFE500` | you name the result and hide the how | YOUR FASTEST SHRED / STARTS WITH LABS |
| Myth question | blue `#4DA3FF` | a belief people hold may be wrong | IS OZEMPIC MADE / FROM LIZARD VENOM? |
| Callout | violet `#A06BFF` | you describe what the viewer is doing wrong | YOU'RE USING CHATGPT / AS A THERAPIST |
| How-to | green `#2FE05F` | a fast, specific method with a number or time | CLEAR ANY EMOTION / IN 90 SECONDS |

More shipped examples to copy the feel from:

- Contrarian: THIS DOCTOR SAYS / MED SCHOOL WAS A WASTE, FOUNDERS USING THIS / WILL DESTROY YOU, NOBODY OWES YOU / SEX
- Receipt: WHAT ONE 'B' / DID TO HIM
- Hidden mechanism: THE ONE THING / AI WON'T TELL YOU, YOUR LEADS GET THIS / BEFORE A SALES CALL
- Myth question: CAN MEN & WOMEN / BE FRIENDS?
- Callout: THE RED FLAG / YOU IGNORE, YOUR NEXT ASSISTANT / ISN'T HUMAN
- Backwards truth (works in Contrarian): CHASING THEM / PUSHES THEM AWAY
- Absolution (works in Callout): NOTHING IS WRONG / WITH YOU

Weak and why: CHATGPT JUST HIRED / AN EMPLOYEE is a news label. It fails 3 of 5 checks.

Before writing a new title, check `hooks/history` in the Room (and any hook list the user keeps) so you do not repeat a hook that already shipped. Extend the shapes that worked instead of inventing new ones.

## Scroll-Stop rubric (5 checks, 2 points each, score 0 to 10)

1. **First 3 words pull.** Read only the first 3 words. Do they create curiosity, surprise or a fight? "I TESTED 47" yes. "HERE'S WHAT I" no.
2. **Two of four hits.** The two lines contain at least two of: a specific number, a push-back claim (disagrees with common belief), the word YOU or YOUR, one emoji.
3. **Withholds the payoff.** It opens a loop. It is not a topic label and does not give the answer away.
4. **Shape.** Exactly 2 lines, 2 to 4 words each, ALL CAPS (emoji and numerals fine).
5. **Answered fast.** The first 10 seconds of the transcript set up an answer that lands within 5 seconds of speech. If no transcript is given, mark this check as "unknown" and count it as a pass.

Verdict:

- **Green** (score 8 or 10): 5 passes, or 4 passes where checks 1 and 3 both pass.
- **Yellow** (score 6): 3 passes, or 4 passes where check 1 or 3 fails.
- **Red** (score 4 or less): 2 or fewer passes.

Always show failing checks in plain words ("Line 1 starts with 'HERE'S WHAT', nothing pulls") and three rewrites in three different categories, each scored by the same rubric.

## Grader prompt (the Room sends this to `sample`)

Fill `{{L1}}`, `{{L2}}`, `{{TITLE}}` (the reel title, may be empty) and `{{TRANSCRIPT}}` (first 10 seconds of speech, may be empty). Send it as one user message.

```
You grade on-screen title hooks for short vertical videos. Reply with JSON only. No prose, no markdown fences, no em dashes.

HOOK
Line 1: {{L1}}
Line 2: {{L2}}
Reel title: {{TITLE}}
First 10 seconds of speech: {{TRANSCRIPT}}

GOAL
A title opens a question in the viewer's head that only the video can close. A title that just labels the topic is dead.

CHECKS (each pass or fail)
1. first3: the first 3 words create curiosity, surprise or a fight.
2. hits: at least two of these are present: a specific number, a claim that pushes back on common belief, the word YOU or YOUR, an emoji.
3. withholds: it hides the payoff and opens a loop. It is not a topic label.
4. shape: exactly 2 lines, 2 to 4 words per line, ALL CAPS.
5. answered: the speech above answers it within 5 seconds. If no speech was given, pass this check and say "no transcript".

SCORE: 2 points per passed check, 0 to 10.
VERDICT: "green" if all 5 pass, or 4 pass with checks 1 and 3 both passing. "yellow" if 3 pass, or 4 pass with check 1 or 3 failing. "red" if 2 or fewer pass.

REWRITES
Give exactly 3 rewrites, each in a different category from this list: Contrarian, Receipt, Hidden mechanism, Myth question, Callout, How-to. Each rewrite is 2 lines, 2 to 4 words per line, ALL CAPS. Do not invent facts, numbers or claims that the speech above does not support. If no speech was given, keep the same topic as the hook. Score each rewrite with the same rules.

OUTPUT (strict JSON, exactly this shape)
{"verdict":"green|yellow|red","score":0,"checks":[{"name":"first3","pass":true,"why":"short plain reason"},{"name":"hits","pass":true,"why":""},{"name":"withholds","pass":true,"why":""},{"name":"shape","pass":true,"why":""},{"name":"answered","pass":true,"why":""}],"rewrites":[{"l1":"","l2":"","category":"","score":0,"why":""},{"l1":"","l2":"","category":"","score":0,"why":""},{"l1":"","l2":"","category":"","score":0,"why":""}]}
```

Page handling rules:

- Strip any code fences, `JSON.parse` the rest. If it fails, retry once. If it fails again, write `hooks/request` for Claude and show "Claude will grade this in chat".
- Recompute `score` and `verdict` in the page from `checks` so a wrong model total cannot show a wrong colour.
- Save each graded hook to `hooks/history`. "Use for A/B" saves `hooks/ab {main, trial}` (two different categories, one for the main reel, one for the trial reel).
