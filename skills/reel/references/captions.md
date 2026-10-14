# Captions: write, grade, loop to 8

This is the whole caption method. It does not depend on any other skill. Use it for the caption that goes with a reel or a carousel. The on-screen title is a different job (see `hook-school.md`). The caption hook must add something, not repeat the title.

## Inputs

- Platform and format: Instagram reel, Instagram carousel, or TikTok.
- The topic and the one idea of the video. Use the transcript, not a guess.
- `brand.json`: name, handle, `cta` (keyword and text). Optional `voice` notes.
- Whether a keyword auto-DM is set up for this post.
- If the topic or platform is missing, ask. Do not invent them.

## Workflow

### 1. Pick the hook pattern

Match the angle to a pattern. When unsure, prefer Receipt, Reverse and Stolen Lesson, they travel furthest.

| If the video has | Use |
|---|---|
| A result, a number, an experiment | Receipt: "I tested 47 scents. Only 3 sold." |
| A strong opinion | Reverse: "Most people think X. They're missing Y." or Reframe: one sentence that flips a belief |
| A thing you copied from someone | Stolen lesson: "I copied X. Here's what happened." |
| A real moment or confession | Story: "I almost shut it down in March." |
| A big claim with a surprising number | Specific number: lead with the number |
| A group that recognises itself | Pain list: stack 2 or 3 pains they know |
| A question they want answered | Question: one they will answer in their head |
| Insider knowledge | "Here's what nobody tells you about X." |

### 2. Draft 3 hooks, test them

1. Write 3 hooks, each from a different pattern.
2. First-3-words test: read only the first 3 words. Do they create curiosity, surprise or a fight? "I tested 47" passes. "Here's what I" fails. "Most people think" passes.
3. Read each aloud. Would you stop for it?
4. Pick one. Cut every filler word. The final hook should have a number, a name or a moment, open a question the reader needs closed, and work alone as a one-line post.

Do not write the body until the hook is strong. A weak hook wastes the body. Do not show the user three versions and ask them to choose. Pick one. Offer another only if asked.

### 3. Write the body

- One idea. A second idea is another post.
- Specific: real numbers, names, moments. Not "many clients", but "the client who emailed me Tuesday".
- Talk to "you" directly.
- Short sentences. Mix in one or two very short ones for rhythm.
- Active voice.
- Pull claims from the video. Do not add facts the speaker did not say.
- Medical or financial claims: keep to what was said on camera, no promised results.

### 4. One CTA, matched to the platform

One CTA per post, never three.

- A keyword auto-DM exists for this post: use the keyword CTA from `brand.json`, for example "Comment AGENT and I'll send you the guide."
- No auto-DM: use a share or save CTA. "Save this for the next time you hire." "Send this to one person who needs it." "Tag someone who needs to hear this."
- Weak, avoid: "What do you think?", "Like and share!", "Let me know in the comments", "Link in bio" with no reason.

### 5. Voice rules (check before grading)

- Contractions: don't, you've, it's.
- Zero em dashes. Use a period, comma or new line.
- Numbers as digits: "5 tips", not "five tips".
- Active voice.
- No filler words: really, very, just, basically, literally, actually, simply.
- No filler openers: "in today's world", "let me tell you", "the truth is", "here's the thing".
- Reads like a person, not a template. No metaphor that does not earn its place.

### 6. Self-grade and loop

Grade the draft with the grader below. Apply the top fixes. Re-grade. Do not hand over a caption under 8.0. If it is under 8, the fix is almost always "rewrite the hook". Then write it to the Room.

## Platform table

| Platform and format | Hook | Length | Hashtags | What it rewards | CTA |
|---|---|---|---|---|---|
| Instagram reel | In the first 125 characters (the part before "more") | Hook plus 3 to 6 short lines | 3 to 5, niche, at the end | Watching to the end, then saves | Keyword if auto-DM, else save or send |
| Instagram carousel | Same first 125 characters. Slide 1 carries the title | 4 to 8 short lines, can be a little longer than a reel | 3 to 5, niche, at the end | Saves, then shares | Keyword if auto-DM, else "Save this for ..." |
| TikTok | Keyword or hook in the first 30 characters | Under 150 characters | 5 max | Watch time and completion | Keyword if auto-DM, else a light comment prompt; the video carries the hook |

Other platforms (X, Threads, LinkedIn, Facebook) are not covered by the Room. If asked, keep hashtags at 0 and tell the user the rules differ.

## The grader

You are harsh and fair. A 7 is good, an 8 is strong, a 9 means almost nothing to fix, a 10 does not exist. A false 8 wastes more time than an honest 5. Grade against these rules only. Do not flag taste.

### Seven dimensions, each 0 to 10

| Dimension | Weight | What to check |
|---|---|---|
| Hook strength | 50% | Do the first 3 to 5 words keep a stranger reading? Specific, surprising, polarising or emotional? Throat-clearing opens ("In today's world", "Let me tell you") score low. Most hooks are 4 to 6. |
| Curiosity and specificity | 10% | Real numbers, names, moments, or vague talk? Does it open a loop and close it? |
| Emotional charge | 10% | Does it make someone feel something: surprise, recognition, vindication, relief, anger? Nothing felt means a low score. |
| Share-worthiness | 10% | Would someone tag a friend, save or screenshot it? "I needed to hear this" is share-worthy. "Informative" is not. |
| Voice match | 10% | Sounds like this person (brand name, handle, voice notes) with a point of view, not any AI for any business. If no voice notes are given, score 7 and say "no voice notes". |
| Polarity | 5% | A reader can nod hard or push back. "Marketing is important" is not polarising. |
| Platform fit | 5% | Hook in the first 125 characters, length, hashtag count, and a CTA that drives the metric this platform rewards. |

### Voice audit (pass or fail each)

1. Em dashes: none anywhere.
2. Contractions used.
3. Numbers as digits.
4. Active voice.
5. Filler words: none of really, very, just, basically, literally, actually, simply.
6. Filler openers: none.
7. Hashtag count within the platform table.

### Score

`score = sum(weight x dimension score) - 0.5 per failed audit rule (at most 3 off)`, kept between 0 and 10, one decimal.

Because the hook is 50%, a 10 hook with a mediocre rest still lands near 7.5, and a 4 hook caps near 7.

### Top 3 fixes

For the three changes that raise the score most: quote the exact current line, say why it hurts (less attention, sounds generic, loses the reader), and give a specific rewrite. Not "improve the hook", but the actual replacement. Do not rewrite the whole caption in the fixes.

### Output format in chat

```
Caption grade: 8.4/10
Hook: [pattern]   Platform: [platform]

[final caption text]

Why it works: [one sentence]
```

Keep the pattern name and grading details out of the caption itself. Show the full scorecard only if the user asks.

## Grader prompt (the Room's Caption tab sends this to `sample`)

Fill `{{PLATFORM}}` (`instagram-reel`, `instagram-carousel` or `tiktok`), `{{CAPTION}}`, `{{VOICE}}` (name, handle and voice notes, may be empty), `{{CTA_MODE}}` (`keyword` or `share-save`) and `{{TRANSCRIPT}}` (first 10 seconds, may be empty). Send as one user message.

```
You grade social media captions for how likely they are to travel. Reply with JSON only. No prose, no markdown fences, no em dashes in your own text. Be harsh and fair: 7 is good, 8 is strong, 9 means almost nothing to fix, 10 does not exist. Do not pad scores.

PLATFORM: {{PLATFORM}}
CTA MODE: {{CTA_MODE}} (keyword = a comment-keyword auto-DM exists, share-save = no auto-DM)
VOICE NOTES: {{VOICE}}
VIDEO SPEECH (first 10 seconds): {{TRANSCRIPT}}

CAPTION
{{CAPTION}}

PLATFORM RULES
instagram-reel: hook within the first 125 characters, 3 to 5 niche hashtags at the end, one CTA.
instagram-carousel: hook within the first 125 characters, 3 to 5 niche hashtags at the end, one CTA.
tiktok: hook or keyword within the first 30 characters, under 150 characters total, 5 hashtags max, one CTA.
A good CTA for keyword mode is a comment-keyword offer. A good CTA for share-save mode is a save or send prompt. Vague CTAs ("what do you think", "like and share") are weak.

DIMENSIONS (score each 0 to 10, use these exact names and weights)
1. Hook strength, weight 50. Would the first 3 to 5 words stop a stranger? Specific, surprising, polarising or emotional. Throat-clearing opens score low.
2. Curiosity and specificity, weight 10. Real numbers, names, moments. Opens and closes a loop.
3. Emotional charge, weight 10.
4. Share-worthiness, weight 10. Would someone tag, save or screenshot it?
5. Voice match, weight 10. If voice notes are empty, score 7 and note "no voice notes".
6. Polarity, weight 5. Is there a position a reader can agree or disagree with?
7. Platform fit, weight 5. Hook position, length, hashtag count, CTA matched to the platform.

VOICE AUDIT (pass true or false for each, give the exact violating text or "" if it passes)
1. Em dashes: none anywhere.
2. Contractions used instead of full forms.
3. Numbers written as digits.
4. Active voice.
5. Filler words: none of really, very, just, basically, literally, actually, simply.
6. Filler openers: none of "in today's world", "let me tell you", "the truth is", "here's the thing".
7. Hashtag count within the platform rules.

SCORE: sum of (weight / 100 x dimension score), minus 0.5 for each failed audit rule (at most 3 total), clamped 0 to 10, one decimal.

FIXES: exactly 3, ranked by impact. "current" is an exact quote from the caption. "why" says what it costs. "fix" is the specific replacement text, not general advice.

REWRITE: the full caption with all fixes applied, same platform, obeying every rule above, using only facts the speech or the original caption supports.

OUTPUT (strict JSON, exactly this shape)
{"score":0.0,"breakdown":[{"dimension":"Hook strength","weight":50,"score":0,"note":""},{"dimension":"Curiosity and specificity","weight":10,"score":0,"note":""},{"dimension":"Emotional charge","weight":10,"score":0,"note":""},{"dimension":"Share-worthiness","weight":10,"score":0,"note":""},{"dimension":"Voice match","weight":10,"score":0,"note":""},{"dimension":"Polarity","weight":5,"score":0,"note":""},{"dimension":"Platform fit","weight":5,"score":0,"note":""}],"audit":[{"rule":"Em dashes","pass":true,"violation":""},{"rule":"Contractions","pass":true,"violation":""},{"rule":"Numbers as digits","pass":true,"violation":""},{"rule":"Active voice","pass":true,"violation":""},{"rule":"Filler words","pass":true,"violation":""},{"rule":"Filler openers","pass":true,"violation":""},{"rule":"Hashtag count","pass":true,"violation":""}],"fixes":[{"current":"","why":"","fix":""},{"current":"","why":"","fix":""},{"current":"","why":"","fix":""}],"rewrite":""}
```

Page handling rules:

- Strip code fences, `JSON.parse` the rest. If it fails, retry once. If it fails again, write a request to the db for Claude and show "Claude will grade this in chat".
- Recompute `score` in the page from `breakdown` and `audit` with the formula above, so a wrong model total never shows. Show the number to one decimal.
- Colour the score: 8.0 or more green, 6.5 to 7.9 yellow, below 6.5 red.
- Run the em dash check in the page itself too (search for the character). Do not trust the model for that one rule.
- "Use rewrite" copies `rewrite` into the caption box and re-grades. Save the accepted text to `caption/current {text, score, notes}`.
