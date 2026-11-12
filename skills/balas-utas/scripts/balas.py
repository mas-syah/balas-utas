#!/usr/bin/env python3
"""Balas Utas: post on Threads and auto-reply to everyone who comments a keyword (e.g. "mau") with a link.

Runs on Zernio comment automations (zernio.com), so replies keep going 24/7 without this computer.
Python 3.9+ standard library only. Commands marked WRITES post or reply publicly on the user's account.

  balas.py setup [--account USERNAME] [--tz Asia/Jakarta]   connect: read the key, pick the Threads account
  balas.py whoami                                           connected account and settings
  balas.py posts                                            recent posts with ids and links
  balas.py plan  CAMPAIGN.json                              show exactly what would be sent (no writes)
  balas.py go    CAMPAIGN.json [--at "2026-11-12 19:00"]    WRITES: schedule the post (local time, default
                                                            +3 min) and bind the auto-reply before it goes live
  balas.py arm   CAMPAIGN.json --post LINK_OR_ID            WRITES: auto-reply on a post already published
  balas.py backlog CAMPAIGN.json --post LINK_OR_ID [--send] matching older comments with no reply; --send WRITES
  balas.py schedule                                         campaigns of this computer with post time and status
  balas.py move  NAME --at "2026-11-12 09:15"               reschedule a post that is not live yet
  balas.py report [--since today|YYYY-MM-DD] [--prefix P]   who got the link, skips, misses (all campaigns)
  balas.py list                                             every automation on the account with stats
  balas.py logs  AUTOMATION_ID                              raw log of one automation
  balas.py off   (AUTOMATION_ID | --prefix P) [--not-before "2026-11-14 20:30"]
                                                            WRITES: pause auto-replies; --not-before makes it
                                                            safe to call from a timer (does nothing earlier)

API key: env ZERNIO_API_KEY, or the file ~/.balas-utas/zernio_key (one line, chmod 600). It is never printed.
Settings: ~/.balas-utas/config.json   Campaign ids: ~/.balas-utas/state.json
"""
import argparse
import datetime as dt
import json
import mimetypes
import os
import pathlib
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

API = "https://zernio.com/api/v1"
HOME = pathlib.Path(os.environ.get("BALAS_UTAS_HOME", "~/.balas-utas")).expanduser()
CONFIG = HOME / "config.json"
STATE = HOME / "state.json"
KEY_FILE = HOME / "zernio_key"
PLACEHOLDERS = ("GANTI", "s.id/xxxx", "LINK_KAMU", "TOPIK_KAMU", "HARI_ACARA", "TANGGAL_ACARA", "TODO")


# ---------- plumbing ----------

def key():
    k = os.environ.get("ZERNIO_API_KEY", "").strip()
    if not k and KEY_FILE.exists():
        k = KEY_FILE.read_text().strip()
    if not k or k in ("KEY_ANDA", "YOUR_KEY"):
        sys.exit(f"No Zernio API key. Put it in {KEY_FILE} (one line) or set ZERNIO_API_KEY.")
    return k


def call(method, path, body=None, **params):
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"{API}{path}{'?' + q if q else ''}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {key()}", "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode() or "{}", strict=False)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            msg = e.read().decode()[:500]
            hint = {401: "the API key is wrong or revoked",
                    402: "Zernio plan limit reached (free plan: 2 social accounts per Zernio account)"}.get(e.code, "")
            sys.exit(f"Zernio {method} {path} -> HTTP {e.code}{' (' + hint + ')' if hint else ''}: {msg}")
        except urllib.error.URLError as e:
            if attempt < 3:
                time.sleep(5)
                continue
            sys.exit(f"Cannot reach Zernio: {e.reason}")


def unwrap(x, name):
    return x.get(name, x) if isinstance(x, dict) else x


def oid(x):
    return x.get("_id") or x.get("id")


def cfg():
    if not CONFIG.exists():
        sys.exit("Not set up yet. Run: balas.py setup")
    return json.loads(CONFIG.read_text())


def tz():
    return ZoneInfo(cfg().get("timezone", "Asia/Jakarta"))


def state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(name, **kv):
    s = state()
    s.setdefault(name, {}).update(kv)
    HOME.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2, ensure_ascii=False))


def local(iso):
    if not iso:
        return "-"
    w = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if not w.tzinfo:
        w = w.replace(tzinfo=dt.timezone.utc)
    return w.astimezone(tz()).strftime("%a %d %b %H:%M")


def when_from(at):
    if at:
        w = dt.datetime.fromisoformat(at)
        return (w if w.tzinfo else w.replace(tzinfo=tz())).astimezone(tz())
    return dt.datetime.now(tz()) + dt.timedelta(minutes=3)


# ---------- campaigns ----------

def load(path):
    p = pathlib.Path(path)
    c = json.loads(p.read_text())
    c.setdefault("name", p.stem)
    replies = [r.strip() for r in c.get("replies", []) if r.strip()]
    if not 1 <= len(replies) <= 6:
        sys.exit("replies: give 1 to 6 texts (Zernio rotates one main reply + up to 5 variations)")
    for t in replies + [c.get("post", "")]:
        for ph in PLACEHOLDERS:
            if ph in t:
                sys.exit(f"still holds a placeholder ({ph}): {t[:80]!r}")
    if len(c.get("post", "")) > 500:
        sys.exit(f"post is {len(c['post'])} characters; Threads allows 500")
    if any(len(r) > 500 for r in replies):
        sys.exit("a reply is longer than 500 characters")
    if not c.get("keywords"):
        sys.exit("keywords: give at least one (an empty list would answer every comment)")
    c["keywords"] = list(dict.fromkeys(k.strip().lower() for k in c["keywords"] if k.strip()))
    c["replies"] = replies
    if c.get("image"):
        img = (p.parent / c["image"]).resolve()
        if not img.exists():
            sys.exit(f"image not found: {img}")
        if img.stat().st_size > 8 * 1024 * 1024:
            sys.exit("image is over 8 MB, the Threads limit")
        c["image_path"] = img
    return c


def automation_body(c, **target):
    s = cfg()
    body = {
        "profileId": s["profileId"], "accountId": s["accountId"], "trigger": "comment", "name": c["name"],
        "keywords": c["keywords"], "matchMode": c.get("matchMode", "word"),
        "excludeKeywords": c.get("excludeKeywords", []),
        "commentReply": c["replies"][0], "commentReplyVariations": c["replies"][1:],
        "postTitle": c.get("post", c["name"])[:80],
        **target,
    }
    if body["matchMode"] == "word":
        body["typoTolerance"] = True
    return body


def matches(c, text):
    t = (text or "").lower()
    mode = c.get("matchMode", "word")

    def hit(k):
        k = k.lower()
        if mode == "exact":
            return t.strip() == k
        if mode == "contains":
            return k in t
        return re.search(rf"(?<!\w){re.escape(k)}(?!\w)", t) is not None
    if any(hit(k) for k in c.get("excludeKeywords", [])):
        return False
    return any(hit(k) for k in c["keywords"])


def show(c):
    print(f"Campaign : {c['name']}")
    if c.get("post"):
        print(f"Post ({len(c['post'])} chars):\n  " + c["post"].replace("\n", "\n  "))
    if c.get("image_path"):
        print(f"Image    : {c['image_path'].name} ({c['image_path'].stat().st_size // 1024} KB)")
    print(f"Fires on : {', '.join(c['keywords'])}  (match: {c.get('matchMode', 'word')})")
    if c.get("excludeKeywords"):
        print(f"Never on : {', '.join(c['excludeKeywords'])}")
    print("Replies (one picked at random per person, {{username}} = commenter):")
    for r in c["replies"]:
        print(f"  - {r}")
    print("Each person gets at most one reply per campaign.")


def recent_posts():
    return call("GET", f"/accounts/{cfg()['accountId']}/posts").get("posts", [])


def resolve_post(ref):
    if ref.isdigit():
        return ref
    code = ref.rstrip("/").split("/post/")[-1].split("?")[0]
    for p in recent_posts():
        if p.get("permalink", "").rstrip("/").endswith(code):
            return p["id"]
    sys.exit(f"{ref} is not among the 25 newest posts; pass its numeric id instead (see `posts`)")


def upload(path):
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    pre = call("POST", "/media/presign", {"filename": path.name, "contentType": ctype, "size": path.stat().st_size})
    req = urllib.request.Request(pre["uploadUrl"], method="PUT", data=path.read_bytes(), headers={"Content-Type": ctype})
    urllib.request.urlopen(req, timeout=600).read()
    return pre["publicUrl"]


# ---------- commands ----------

def cmd_setup(a):
    key()
    accts = unwrap(call("GET", "/accounts"), "accounts")
    threads = [x for x in accts if x.get("platform") == "threads"]
    if not threads:
        sys.exit("This Zernio account has no Threads account connected. Connect it at zernio.com first.")
    if a.account:
        threads = [x for x in threads if (x.get("username") or "").lstrip("@").lower() == a.account.lstrip("@").lower()]
        if not threads:
            sys.exit(f"No connected Threads account named {a.account}")
    if len(threads) > 1:
        print("Several Threads accounts are connected; run again with --account USERNAME:")
        for x in threads:
            print("  @" + (x.get("username") or "?"))
        sys.exit(1)
    t = threads[0]
    prof = t.get("profileId")
    prof = oid(prof) if isinstance(prof, dict) else prof
    zone = a.tz or (cfg().get("timezone") if CONFIG.exists() else None) or "Asia/Jakarta"
    ZoneInfo(zone)
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"accountId": oid(t), "profileId": prof, "username": t.get("username"),
                                  "timezone": zone}, indent=2))
    print(f"Connected to Threads @{t.get('username')} (time zone {zone}). Settings in {CONFIG}")


def cmd_whoami(a):
    s = cfg()
    print(f"@{s['username']}  account {s['accountId']}  profile {s['profileId']}  tz {s['timezone']}")


def cmd_posts(a):
    for p in recent_posts()[:15]:
        print(local(p.get("createdTime")), p["id"], p.get("permalink"), "|", (p.get("message") or "")[:60].replace("\n", " "))


def cmd_plan(a):
    show(load(a.campaign))


def cmd_go(a):
    c = load(a.campaign)
    s = cfg()
    if not c.get("post"):
        sys.exit("campaign has no post text")
    if state().get(c["name"], {}).get("postId"):
        sys.exit(f"campaign {c['name']!r} was already posted; give the file another name to post again")
    when = when_from(a.at)
    if when < dt.datetime.now(tz()) + dt.timedelta(minutes=2):
        sys.exit("--at must be at least 2 minutes ahead, so the auto-reply is bound before the post goes live")
    body = {"content": c["post"], "platforms": [{"platform": "threads", "accountId": s["accountId"]}],
            "scheduledFor": when.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": s["timezone"]}
    if c.get("image_path"):
        body["mediaItems"] = [{"type": "image", "url": upload(c["image_path"])}]
    post = unwrap(call("POST", "/posts", body), "post")
    pid = oid(post)
    save_state(c["name"], postId=pid, scheduledFor=when.isoformat())
    auto = unwrap(call("POST", "/comment-automations", automation_body(c, postId=pid)), "automation")
    save_state(c["name"], automationId=oid(auto))
    print(f"{c['name']}: post scheduled {when:%a %d %b %H:%M} ({s['timezone']}), Zernio post {pid}; "
          f"auto-reply {oid(auto)} arms itself when it goes live.")


def cmd_arm(a):
    c = load(a.campaign)
    ppid = resolve_post(a.post)
    auto = unwrap(call("POST", "/comment-automations", automation_body(c, platformPostId=ppid)), "automation")
    save_state(c["name"], platformPostId=ppid, automationId=oid(auto))
    print(f"Auto-reply {oid(auto)} is live on post {ppid}. It answers comments from now on; "
          "for earlier ones run `backlog`.")


def cmd_backlog(a):
    c = load(a.campaign)
    s = cfg()
    ppid = resolve_post(a.post)
    rows = call("GET", "/inbox/comments", profileId=s["profileId"], limit=100)
    pid = next((r["id"] for r in rows.get("data", rows.get("posts", []))
                if str(r.get("platformPostId") or r.get("id")) == str(ppid)), ppid)
    data = call("GET", f"/inbox/comments/{pid}", accountId=s["accountId"])
    me = s["username"]
    todo, seen = [], set()
    for cm in data.get("comments", data.get("data", [])):
        who = (cm.get("from") or {}).get("username") or ""
        if who == me or not cm.get("canReply", True):
            continue
        if any((r.get("from") or {}).get("username") == me for r in cm.get("replies", [])):
            continue
        if who in seen or not matches(c, cm.get("message") or cm.get("text")):
            continue
        seen.add(who)
        todo.append((cm, who))
    print(f"{len(todo)} matching comments without a reply from @{me}:")
    for cm, who in todo:
        print(f"  @{who}: {(cm.get('message') or cm.get('text') or '')[:80]!r}")
    if not a.send or not todo:
        if todo:
            print("Nothing sent. Add --send to reply to these, about one per 75 seconds.")
        return
    for i, (cm, who) in enumerate(todo, 1):
        text = random.choice(c["replies"]).replace("{{username}}", who)
        call("POST", f"/inbox/comments/{pid}", {"accountId": s["accountId"], "message": text, "commentId": cm["id"]})
        print(f"[{i}/{len(todo)}] replied to @{who}")
        if i < len(todo):
            time.sleep(random.uniform(60, 90))


def cmd_schedule(a):
    rows = []
    for name, s in state().items():
        if a.prefix and not name.startswith(a.prefix):
            continue
        if s.get("postId"):
            p = unwrap(call("GET", f"/posts/{s['postId']}"), "post")
            rows.append((p.get("scheduledFor") or "", name, p.get("status"), len(p.get("mediaItems") or [])))
            time.sleep(0.8)
        else:
            rows.append(("", name, "existing post", 0))
    for when, name, status, media in sorted(rows):
        print(f"{local(when):18} {status:10} {'img' if media else '   '} {name}")


def cmd_move(a):
    s = state().get(a.name)
    if not s or not s.get("postId"):
        sys.exit(f"no scheduled post for campaign {a.name!r}")
    p = unwrap(call("GET", f"/posts/{s['postId']}"), "post")
    if p.get("status") != "scheduled":
        sys.exit(f"post is {p.get('status')}, only scheduled posts can be moved")
    when = when_from(a.at)
    if when < dt.datetime.now(tz()) + dt.timedelta(minutes=2):
        sys.exit("new time must be at least 2 minutes ahead")
    call("PUT", f"/posts/{s['postId']}", {"scheduledFor": when.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": cfg()["timezone"]})
    save_state(a.name, scheduledFor=when.isoformat())
    print(f"{a.name}: moved to {when:%a %d %b %H:%M}")


def logs_of(aid):
    out, misses = [], {}
    while True:
        d = call("GET", f"/comment-automations/{aid}/logs", limit=100, skip=len(out))
        got = d.get("logs", [])
        out += got
        misses = d.get("misses") or misses
        if not got or not (d.get("pagination") or {}).get("hasMore") or len(out) > 5000:
            return out, misses


def cmd_report(a):
    since = None
    if a.since == "today":
        since = dt.datetime.now(tz()).replace(hour=0, minute=0, second=0, microsecond=0)
    elif a.since:
        since = dt.datetime.fromisoformat(a.since).replace(tzinfo=tz())
    totals, people, rows, misses = {}, set(), [], []
    for name, s in state().items():
        if a.prefix and not name.startswith(a.prefix) or not s.get("automationId"):
            continue
        logs, m = logs_of(s["automationId"])
        for lg in logs:
            w = dt.datetime.fromisoformat(lg["createdAt"].replace("Z", "+00:00"))
            if since and w < since:
                continue
            st = lg.get("status")
            totals[st] = totals.get(st, 0) + 1
            who = lg.get("commenterUsername") or lg.get("commenterName")
            if st == "sent":
                people.add(who)
            rows.append((w, name, st, who, (lg.get("commentText") or "")[:50]))
        misses += [(name, x) for x in m.get("samples", [])]
        time.sleep(0.8)
    for w, name, st, who, text in sorted(rows):
        print(f"{w.astimezone(tz()):%a %d %H:%M}  {st:8} @{who:22} {text!r}  [{name}]")
    print(f"\nTotal: {totals or 'nothing yet'}; {len(people)} people got the link.")
    if misses:
        print("Comments that matched no keyword (consider adding a keyword):")
        for name, x in misses[:15]:
            print(f"  {x.get('commenterName')}: {x.get('commentText')!r} [{name}]")


def cmd_list(a):
    for au in call("GET", "/comment-automations", profileId=cfg()["profileId"]).get("automations", []):
        print(oid(au), "ON " if au.get("isActive") else "OFF", au.get("name"), "| stats", json.dumps(au.get("stats", {})))


def cmd_logs(a):
    logs, m = logs_of(a.automation)
    for lg in logs:
        print(local(lg.get("createdAt")), lg.get("status"), "@" + str(lg.get("commenterUsername") or lg.get("commenterName")),
              repr((lg.get("commentText") or "")[:60]))
    if m.get("total"):
        print(f"\n{m['total']} comments matched no keyword, e.g.:")
        for x in m.get("samples", []):
            print(f"  {x.get('commenterName')}: {x.get('commentText')!r}")


def cmd_off(a):
    if a.not_before and dt.datetime.now(tz()) < when_from(a.not_before):
        print(f"Too early (before {a.not_before}); nothing paused.")
        return
    ids = [a.automation] if a.automation else [s["automationId"] for n, s in state().items()
                                               if n.startswith(a.prefix or "\0") and s.get("automationId")]
    if not ids:
        sys.exit("nothing to pause (give an automation id or a --prefix that matches campaign names)")
    for i in ids:
        call("PATCH", f"/comment-automations/{i}", {"isActive": False})
        print(f"Paused {i}")
        time.sleep(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup")
    p.add_argument("--account")
    p.add_argument("--tz")
    for n in ("whoami", "posts", "list"):
        sub.add_parser(n)
    for n in ("plan", "go", "arm", "backlog"):
        p = sub.add_parser(n)
        p.add_argument("campaign")
        if n == "go":
            p.add_argument("--at")
        if n in ("arm", "backlog"):
            p.add_argument("--post", required=True)
        if n == "backlog":
            p.add_argument("--send", action="store_true")
    sub.add_parser("schedule").add_argument("--prefix")
    p = sub.add_parser("move")
    p.add_argument("name")
    p.add_argument("--at", required=True)
    p = sub.add_parser("report")
    p.add_argument("--since")
    p.add_argument("--prefix")
    sub.add_parser("logs").add_argument("automation")
    p = sub.add_parser("off")
    p.add_argument("automation", nargs="?")
    p.add_argument("--prefix")
    p.add_argument("--not-before")
    a = ap.parse_args()
    globals()[f"cmd_{a.cmd}"](a)


if __name__ == "__main__":
    main()
