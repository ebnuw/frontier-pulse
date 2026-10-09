"""Fetch fresh news headlines for entities with markets on Entropy.

Google News RSS (no auth). One query per entity, deduped across queries,
stored in data/news.json with the fetch timestamp. Failures degrade to an
empty list — the site just hides the section.
"""
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape

from .common import DATA, save_json, site_cfg, valuations_cfg

NEWS = DATA / "news.json"
MAX_PER_ENTITY = 2
MAX_AGE_S = 14 * 86400

# search phrase + site blocklist for paywalled/noisy domains
QUERIES = {
    "io:ANTH": {"q": "Anthropic", "name": "Anthropic", "blocked": ("yahoo.", "msn.com")},
    "io:OAI": {"q": "OpenAI", "name": "OpenAI", "blocked": ("yahoo.", "msn.com")},
}
EXTRA = {  # equities etc: keep it light, these rotate
    "Nvidia": {"q": "Nvidia stock OR earnings", "blocked": ("yahoo.", "msn.com")},
}


def _fetch(query, blocked, limit):
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
           + "+when:3d&hl=en-US&gl=US&ceid=US:en")
    req = urllib.request.Request(url, headers={"User-Agent": "frontier-pulse/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        root = ET.fromstring(r.read().decode("utf-8", "replace"))
    out = []
    seen_titles = set()
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        source = (it.findtext("source") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate") or ""
        # Google News titles end with " - Source"; strip it, keep source separate
        if title.endswith(" - " + source) and len(source) < 40:
            title = title[: -len(source) - 3].strip()
        key = title.lower()[:60]
        if not title or key in seen_titles:
            continue
        if any(b in link or b in source.lower() for b in blocked):
            continue
        try:
            ts = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
        if time.time() - ts > MAX_AGE_S:
            continue
        seen_titles.add(key)
        out.append({"title": title, "source": source, "url": link, "ts": ts,
                    "entity": query})
        if len(out) >= limit:
            break
    return out


def fetch_all(force=False):
    cfg = site_cfg()
    vcfg = valuations_cfg()
    for sym in cfg["pre_ipo"]:
        if sym not in QUERIES:
            QUERIES[sym] = {"q": vcfg["assets"][sym].get("short", sym.split(":")[1]),
                            "name": vcfg["assets"][sym].get("short", sym.split(":")[1]),
                            "blocked": ("yahoo.", "msn.com")}
    items, seen = [], set()
    for sym, c in QUERIES.items():
        try:
            for it in _fetch(c["q"], c["blocked"], MAX_PER_ENTITY + 2):
                key = it["title"].lower()[:60]
                if key in seen:
                    continue
                seen.add(key)
                it["entity"] = c["q"]
                it["name"] = c.get("name", c["q"])
                items.append(it)
        except Exception:
            continue  # one dead feed never kills the build
    for name, c in EXTRA.items():
        try:
            for it in _fetch(c["q"], c["blocked"], 1):
                key = it["title"].lower()[:60]
                if key in seen:
                    continue
                seen.add(key)
                it["entity"] = c["q"]
                it["name"] = name
                items.append(it)
        except Exception:
            continue
    items.sort(key=lambda x: -x["ts"])
    payload = {"ts": time.time(), "items": items[:8]}
    save_json(NEWS, payload)
    return payload


def load():
    try:
        return json.loads(NEWS.read_text())
    except Exception:
        return {"ts": 0, "items": []}


def run(force=False):
    DATA.mkdir(exist_ok=True)
    cur = load()
    if not force and cur.get("ts") and time.time() - cur["ts"] < 6 * 3600:
        return NEWS, False
    fetch_all(force=force)
    return NEWS, True


def _unused():
    unescape("")


if __name__ == "__main__":
    import sys
    p, w = run(force="--force" in sys.argv)
    print(p if w else f"{p} (fresh, skipped)")
    print(json.dumps(load()["items"][:3], indent=1)[:500])
