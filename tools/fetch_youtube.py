"""
🏝 Остров подписчиков (YouTube) — сбор комментов канала через YouTube Data API v3.

Переменные окружения:
  YT_API_KEY     — ключ API (Google Cloud → YouTube Data API v3 → Credentials → API key)
  YT_CHANNEL_ID  — id канала (UC...)

Пишет рядом:
  comments.json  — все комменты (id, reel=videoId, username=handle без @, text, time)
  residents.json — жители по порядку первого коммента; номера не меняются
  stats.json     — подписчики канала
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://www.googleapis.com/youtube/v3/"
MAX_PAGES = int(os.environ.get("YT_MAX_PAGES", "10"))  # 100 комментов на страницу, 1 ед. квоты за запрос
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def get(path, **params):
    params["key"] = os.environ["YT_API_KEY"]
    url = API + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def load(name, default):
    f = HERE / name
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_atomic(path, text):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def handle(snippet):
    """@handle → handle (lowercase); old channels without a handle keep their display name."""
    name = (snippet.get("authorDisplayName") or "").strip()
    return name.lstrip("@").lower()


def main():
    channel = os.environ["YT_CHANNEL_ID"]
    me = get("channels", part="statistics,snippet", id=channel)["items"][0]
    own_ch = channel

    comments = {c["id"]: c for c in load("comments.json", [])}
    page, n = None, 0
    while n < MAX_PAGES:
        params = dict(part="snippet,replies", allThreadsRelatedToChannelId=channel, maxResults=100,
                      order="time", textFormat="plainText")
        if page:
            params["pageToken"] = page
        data = get("commentThreads", **params)
        n += 1
        known = 0
        for th in data.get("items", []):
            top = th["snippet"]["topLevelComment"]
            items = [top] + th.get("replies", {}).get("comments", [])
            for x in items:
                s = x["snippet"]
                author = (s.get("authorChannelId") or {}).get("value")
                if x["id"] in comments:
                    known += 1
                if not author or author == own_ch:
                    continue  # the channel's own replies never make a resident
                comments[x["id"]] = {"id": x["id"], "reel": th["snippet"].get("videoId", ""), "author": author,
                                     "username": handle(s), "text": s.get("textOriginal", ""), "time": s["publishedAt"]}
        page = data.get("nextPageToken")
        if not page or known >= len(data.get("items", [])):
            break  # reached comments we already have

    rows = sorted(comments.values(), key=lambda c: c["time"])

    # residents: one per YouTube channel (author id), numbered by first comment; a renamed handle keeps the house
    old = load("residents.json", [])
    by_author = {r["author"]: r for r in old if r.get("author")}
    next_no = max([r["no"] for r in old] + [1]) + 1  # №1 — сам остров
    latest = {c["author"]: c["username"] for c in rows}
    new = 0
    for c in rows:
        a = c["author"]
        if a not in by_author:
            by_author[a] = {"no": next_no, "nick": c["username"], "since": c["time"], "reel": c["reel"], "author": a}
            next_no += 1
            new += 1
    taken = set()
    for r in sorted(by_author.values(), key=lambda r: r["no"]):
        nick = latest.get(r["author"], r["nick"])
        r["nick"] = nick if nick not in taken else f"{nick}_{r['no']}"
        taken.add(r["nick"])
    # build_map.py looks up comments by nick: give every comment its author's current nick
    nick_of = {r["author"]: r["nick"] for r in by_author.values()}
    for c in rows:
        c["username"] = nick_of.get(c["author"], c["username"])
    write_atomic(HERE / "comments.json", json.dumps(rows, ensure_ascii=False, indent=0))

    res = sorted(by_author.values(), key=lambda r: r["no"])
    write_atomic(HERE / "residents.json", json.dumps(res, ensure_ascii=False, indent=1))
    subs = me.get("statistics", {}).get("subscriberCount")
    write_atomic(HERE / "stats.json", json.dumps({"followers": int(subs) if subs else None, "residents": len(res) + 1}))
    print(f"✅ Комментов: {len(rows)}, жителей: {len(res) + 1} (новых: {new}), подписчиков: {subs}")


if __name__ == "__main__":
    main()
