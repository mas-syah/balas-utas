---
name: balas-utas
description: Promote an event, freebie or link on Threads with a "reply 'mau' and I'll send you the link" post, and auto-reply to every commenter with the link through Zernio - write short casual post variations, schedule them, bind the auto-reply before each goes live, check who got the link, reschedule, and stop everything after the event. Use when the user says "balas utas", "auto reply threads", "komen mau dapat link", "jadwalkan utas", "cek balasan", "variasi utas", "majukan jadwal", or wants comment-to-link automation on Threads.
---

# Balas Utas (Threads comment → link)

The pattern: a short post asks people to reply a keyword ("mau"); everyone who does gets a public reply with the
link within seconds. Zernio runs the replies on its servers, so they keep working when this computer is off.
Speak the user's language (Indonesian by default); post and reply texts are in the audience's language.

The command line is `python3 <this skill folder>/scripts/balas.py` (call it `balas` below; `balas -h` lists all).
Campaign files live in a folder the user picks (default `~/balas-utas/campaigns/`). Ids are kept in
`~/.balas-utas/state.json`, so always run commands through `balas`, never by hand-editing that file.

## Safety rules (always)
- Posting, replying and pausing are public actions on the user's account. Show the exact texts and times and get a
  clear yes before `go`, `arm`, `backlog --send`, `move` or `off`. A yes covers what you showed, nothing more.
- Never type, print or paste the Zernio API key. The user puts it in `~/.balas-utas/zernio_key` themselves.
- Never invent the link, date, speaker or quota. Ask. Don't claim "kuota tinggal sedikit" unless the user says so.

## 1. First time on this computer
1. Python 3.9+ is needed (`python3 --version`).
2. The user needs a Zernio account (zernio.com, free plan is fine: 2 social accounts) with their Threads account
   connected, and an API key from Zernio's settings.
3. Ask them to save the key themselves, in their own terminal:
   `mkdir -p ~/.balas-utas && nano ~/.balas-utas/zernio_key` (paste, save), then `chmod 600 ~/.balas-utas/zernio_key`.
   On Windows: create `%USERPROFILE%\.balas-utas\zernio_key` in Notepad.
4. Run `balas setup` (add `--account USERNAME` if several Threads accounts are connected, `--tz Asia/Jakarta` or
   another IANA zone; times in every command are in this zone).

## 2. Write the campaign
Collect: what is offered, date/time, the link, who it is for, and any poster image. Then write a campaign file per
post (see `templates/contoh.json`):

```json
{ "name": "webinar-s01", "post": "...", "image": "poster.jpg (optional, relative to the file)",
  "keywords": [...], "matchMode": "word", "excludeKeywords": [...], "replies": ["...", "..."] }
```

Post style that works on Threads (from posts that got 40-100+ replies):
- Short (1-3 lines + the ask), casual, lowercase is fine, ".." instead of formal punctuation, few or no emoji.
- Open with the audience and an invitation: "temen temen IT, ada yang mau diajakin belajar ... GRATIS?"
- One concrete detail (topic, day/date, online), then the ask on its own line: `yang berminat reply "mau" ya..`
- No link in the post (that is what the reply is for), no hashtags, under 500 characters.
- Text-only posts feel like conversation; a poster suits one or two of the more formal versions.
- Each post needs its own wording. Write 8-12 variations with different openings (question, problem, audience
  call-out, "malem ini", "besok", list of what you'll learn), and mark time-bound ones (H-1, same day).

Keywords: start from `templates/contoh.json` (mau, ikut, minat, join, daftar, link, gas, boleh, tertarik, 🙋 ...)
and excludes (gak mau, ga bisa ...). `matchMode` "word" matches whole words and tolerates typos.

Replies: 5-6 per campaign (Zernio picks one at random), each with `@{{username}}` and the link, in the same tone as
the post. Vary the order or wording per campaign so threads don't all answer identically. Each person is answered
once per campaign; someone who comments on two posts gets the link twice, which is fine.

Show every post and its replies (`balas plan FILE` prints exactly what will be sent) before asking for the yes.

## 3. Schedule
- `balas go FILE --at "YYYY-MM-DD HH:MM"` per campaign. It schedules the post and binds the auto-reply to it first,
  so no comment is missed. Times must be at least 2 minutes ahead; without `--at` it posts in 3 minutes.
- Spread variations about 2 hours apart, between ~07:00 and ~22:00, ending before the event; put "besok" posts on
  the day before and "malem ini" posts on the day itself. Say the full timetable in a table.
- 10+ similar promo posts in two days can look like spam; mention it once and let the user decide.
- `balas schedule` shows every campaign with its time and status (scheduled / published).
- Move a post that is not live yet: `balas move NAME --at "..."` (its auto-reply follows automatically).

## 4. Already published in the Threads app?
`balas arm FILE --post <threads.com link>` turns on the auto-reply for comments from now on. `balas backlog FILE
--post <link>` lists earlier matching comments with no reply; `--send` answers them slowly (needs a yes).

## 5. "Cek balasan"
`balas report` (all campaigns) or `balas report --since today` / `--prefix webinar-`. Summarise for the user: who
got the link (time, name, comment), skips (same person again), failures, and comments that matched no keyword. If
a miss is clearly interested ("wah menarik", "pengen"), propose adding that word and, on a yes, update the
automation (`PATCH /comment-automations/{id}` with the new `keywords`; edit the campaign file too).

## 6. Stop after the event
Auto-replies stay on until paused. Pause all campaigns of one event: `balas off --prefix webinar-`.
To do it automatically, offer a one-off timer that calls
`balas off --prefix webinar- --not-before "YYYY-MM-DD HH:MM"` at that time (the guard makes an early run harmless):
- macOS: a LaunchAgent plist in `~/Library/LaunchAgents` with `StartCalendarInterval` (Month/Day/Hour/Minute),
  loaded with `launchctl bootstrap gui/$(id -u) <plist>`; it runs on wake if the Mac was asleep.
- Linux: `systemd-run --user --on-calendar="YYYY-MM-DD HH:MM" ...` or `at`.
- Windows: `schtasks /create /sc once /st HH:MM /sd DD/MM/YYYY /tn balas-utas-stop /tr "python ..."`.
Tell the user the computer must be on (or wake) for the timer; otherwise ask them to say "matikan" afterwards.

## Limits worth knowing
- Replies are public replies, not DMs (Threads has no DM API).
- Zernio answers only comments made while the automation is on; that is why posts are always scheduled ahead.
- One automation per post. Zernio's free plan allows 2 social accounts per Zernio account; HTTP 402 means full.
- Rate limit about 60 requests a minute; `balas` waits and retries on 429.
