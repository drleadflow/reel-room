# Posting

Posting is public. Claude never posts without a clear yes in chat that names the account, file, cover, caption and time.

Files come from `renders/` after `deliver.py`: `-share.mp4` (post this), `-silent.mp4` (for trending sounds), `-cover.png` or the cover picked in the Room, `.srt`, and the caption text from the Room's Cover + caption tab.

## Manual, from your phone

1. Open the Room on your phone, Downloads tab. Save the share video and the cover image to your camera roll.
2. Instagram: + then Reel, pick the video.
3. Cover: tap Edit cover, then Add from camera roll, pick the cover image. Check the title sits inside the visible area of the profile grid crop.
4. Caption: paste from the Room (Copy button). First line is the hook, so it shows before "more".
5. Trial reel (optional): on the final share screen turn on Trial. A trial reel is shown to people who do not follow you first. If it does well you can share it to followers. Good use: post the hook B version as a trial.
6. Trending sound: use the silent version. Pick the sound in the app, set the original audio volume to 0 or low, and make sure captions are already burned in. Your voice is not in the silent version, so only use it when the sound is the point.
7. Share. Pin a first comment with the keyword prompt if the CTA asks for one.

### Carousels

Upload the slide images in order (1080x1350). Slide 1 is the hook. Add music in the app if wanted. Put the CTA on the last slide and in the caption. A reel and a carousel on the same idea in the same week reuses the work.

## Zernio (optional, automatic)

Zernio schedules and publishes for you. Sign up with the affiliate link: https://zernio.link/emeka-ajufo

Setup:

- Connect the Instagram account in Zernio. Note the account id it shows.
- Put the API key in your environment as `ZERNIO_API_KEY`. Never paste it in chat, never write it in a project file. The engine never prints it.
- Without a key, `post.py` prints the affiliate link and the manual steps instead.

What `post.py` does (run through the venv python):

1. Uploads the video and the cover with a presigned upload, gets public URLs.
2. Creates the post with the caption, the video, and the custom cover in `platformSpecificData.instagramThumbnail`. `shareToFeed` is on.
3. `--trial` posts as an Instagram trial reel.
4. Modes: draft (nothing goes public, default for a first test), publish now, or schedule with an ISO time and a timezone name, for example `2026-10-09T12:00:00 America/New_York`.
5. Carousel mode takes images in order instead of a video.

Notes:

- Draft first the first time, look at it in Zernio, then publish.
- Catalog audio (the trending sound library) needs the Instagram account connected through Facebook login. If yours is not, post the silent version and add the sound in the app, or use the manual steps.
- Upload size: keep the share file under 30 MB. Presigned uploads of big files can time out on slow wifi, retry once before changing anything.
- If a post fails, `post.py` prints the status and Zernio's message. Do not retry blindly: check whether the post already exists in Zernio first, to avoid a double post.

### Comment-to-DM keyword

The usual loop: the on-screen CTA and the caption say "Comment KEYWORD" (the keyword is in `brand.json`). An automation watches comments on that post. When the keyword appears it replies to the comment and sends one DM with one link. Basics that save pain:

- One keyword per post, short, easy to type.
- One link in the DM. Put the community or next step inside the resource, not in the DM.
- Set it up after the post is live, so the automation can point at the real post id.
- Test it with a second account before you tell people to comment.

## When to post

- There is no magic hour. Look at your own Instagram Insights, Total followers, Most active times, and post inside the top window for your audience's time zone.
- Mornings before work and evenings after work are the usual peaks. Test two slots for two weeks and keep the better one.
- Be consistent. Same days and similar times beat random bursts.
- Trial reel first for a risky hook, then repost the winner to followers.
- Reply to comments in the first hour. It helps and it feeds the keyword automation.
