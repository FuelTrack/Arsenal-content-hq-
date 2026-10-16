#!/usr/bin/env python3
"""Build a public Arsenal headlines snapshot from Google News RSS search feeds."""
import datetime as dt
import email.utils
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

QUERIES = [
    "Arsenal FC when:2d",
    "Arsenal transfer when:2d",
    "Arsenal injury OR team news when:2d",
    "Arsenal site:arsenal.com when:3d",
    "Arsenal site:bbc.co.uk/sport when:3d",
    "Arsenal site:skysports.com when:3d",
    "Arsenal David Ornstein when:3d",
]
CUTOFF_DAYS = 4
NOW = dt.datetime.now(dt.timezone.utc)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ArsenalContentHQ/1.0; news aggregation)"}

def get_feed(query):
    params = urllib.parse.urlencode({"q": query, "hl": "en-GB", "gl": "GB", "ceid": "GB:en"})
    req = urllib.request.Request("https://news.google.com/rss/search?" + params, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=18) as response:
        return ET.fromstring(response.read(2_000_000))

def clean_title(title, source):
    suffix = " - " + source
    return title[:-len(suffix)].strip() if source and title.endswith(suffix) else title.strip()

def category(title):
    s = title.lower()
    if any(x in s for x in ("injur", "fitness", "sidelined", "team news", "lineup", "line-up")):
        return "Team news"
    if any(x in s for x in ("transfer", "signing", "bid ", "deal ", "target", "contract")):
        return "Transfers"
    if any(x in s for x in ("match", "fixture", "preview", "win over", "defeat", "goal", "champions league")):
        return "Matches"
    return "General"

items = []
errors = []
seen = set()
for query in QUERIES:
    try:
        root = get_feed(query)
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            source = (item.findtext("source") or "Google News").strip()
            published = (item.findtext("pubDate") or "").strip()
            if not title or not link.startswith("https://"):
                continue
            try:
                date = email.utils.parsedate_to_datetime(published).astimezone(dt.timezone.utc)
            except (ValueError, TypeError, AttributeError):
                continue
            if date < NOW - dt.timedelta(days=CUTOFF_DAYS) or date > NOW + dt.timedelta(hours=2):
                continue
            title = clean_title(title, source)
            key = re.sub(r"[^a-z0-9]+", "", title.lower())[:115]
            if not key or key in seen:
                continue
            seen.add(key)
            items.append({"title": title, "url": link, "source": source, "published": date.isoformat(), "category": category(title)})
    except Exception as exc:
        errors.append(f"{query}: {type(exc).__name__}: {exc}")
    time.sleep(0.4)

items.sort(key=lambda i: i["published"], reverse=True)
path = Path("news.json")
if not items:
    if path.exists():
        print("No fresh items fetched; preserving last known feed. Errors:", errors)
        raise SystemExit(0)
    raise SystemExit("No news fetched and no previous snapshot exists: " + "; ".join(errors))
payload = {"updated_at": NOW.isoformat(), "count": len(items[:100]), "articles": items[:100]}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Saved {payload['count']} articles; errors: {errors}")
