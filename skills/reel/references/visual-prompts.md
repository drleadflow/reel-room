# Generated visuals (images and B-roll)

Use this only when a beat needs a visual the user does not have and the user agreed to generate one. Real footage, real
screenshots and real photos come first.

## 1. Lock the series style once per project

Ask once, save in `project.json` as `visual_style`, reuse for every visual of the reel:

```json
"visual_style": {
  "style": "photoreal editorial",
  "palette": "warm neutrals, one accent from brand.json, soft window light",
  "format": "9:16, subject in the top half",
  "people": "no people unless the line needs a person; hands are fine"
}
```
Offer defaults from `brand.json` so the user can say "ok". Every visual in the reel uses the same lock.

## 2. Write the intent first, get a yes, then spend credits

For each beat that needs a generated visual, write one sentence into the storyboard beat as `visual_intent`: what the
viewer will see, not how it is made ("A real fasting insulin lab line, the number circled"). The Room shows it under the
beat. Generate only after the storyboard is approved with that intent in it. A changed intent is a changed storyboard.

## 3. The prompt

Build it from these parts, in this order:

1. The style lock, word for word.
2. The full script, so the visual fits the whole story.
3. The one line this visual plays under.
4. What to show. Rules:
   - Show what the line is about. Do not repeat the spoken words on screen.
   - Text inside the image only when it is needed to understand it (a label, a number, a name). Short, spelled exactly.
   - Real products, apps, places, processes and numbers look the way they really are. If you are not sure what
     something looks like, ask the user or use a real screenshot instead.
   - One focal point. It must read in a second on a phone.
   - Same palette, light and feel as every other visual in the series.
5. Never include:
   - stock photo clichés and filler props
   - quotes or slogans on walls, mugs, screens, signs or clothing
   - fake or gibberish text
   - warped hands or faces, plastic shine, the obvious AI look
   - cheesy futuristic effects that do not fit the topic
   - extra objects that pull the eye away from the point
   - anything on the user's own never list (`brand.json` `lessons` or the style lock)

## 4. Health and people rules

- No AI-generated doctors, patients, or AI versions of the creator. Use the creator's own footage or no person.
- A real client's face only with their consent, confirmed by the user in chat.
- No before/after bodies, no fake lab results, no invented numbers. Proof must be real proof.
- Medical claims in the line stay as said (SKILL.md hard rules). The visual must not add a claim the creator did not make.

## 5. Check before it goes in

Look at every generated visual at phone size before it goes in a beat: one focal point, no gibberish text, hands and
faces normal, matches the series. Reject and regenerate rather than ship a weak one. Two failed tries: tell the user
and offer presenter only for that beat.
