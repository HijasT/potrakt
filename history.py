import json
import time

from paths import app_dir

LOG_PATH = app_dir() / "history.jsonl"


def log_event(event, **fields):
    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **fields}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _item_key(entry):
    kind = entry.get("kind")
    ids = entry.get("ids") or {}
    trakt_id = ids.get("trakt")
    if kind == "episode":
        return ("episode", trakt_id, entry.get("season"), entry.get("episode"), entry.get("title"))
    return ("movie", trakt_id, entry.get("title"), entry.get("year"))


def _media_from_bucket(bucket):
    media = {"kind": bucket.get("kind"), "title": bucket.get("title"), "ids": bucket.get("ids")}
    if bucket.get("kind") == "episode":
        media["season"] = bucket.get("season")
        media["episode"] = bucket.get("episode")
    else:
        media["year"] = bucket.get("year")
    return media


def load_summary():
    """Aggregate the raw event log into one row per watched item, most recent first."""
    if not LOG_PATH.exists():
        return []

    items = {}
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        key = _item_key(entry)
        bucket = items.setdefault(key, {"progress": 0, "rating": None})
        bucket["kind"] = entry.get("kind")
        bucket["title"] = entry.get("title")
        bucket["season"] = entry.get("season")
        bucket["episode"] = entry.get("episode")
        bucket["year"] = entry.get("year")
        bucket["ids"] = entry.get("ids") or bucket.get("ids")

        if entry.get("event") == "rated":
            bucket["rating"] = entry.get("rating")
            bucket.setdefault("time", entry["time"])
        elif entry.get("event") in ("start", "pause", "stop"):
            bucket["time"] = entry["time"]
            bucket["progress"] = max(bucket.get("progress", 0), entry.get("progress", 0))

    summary = [
        {
            "time": bucket.get("time", ""),
            "media": _media_from_bucket(bucket),
            "progress": bucket.get("progress", 0),
            "rating": bucket.get("rating"),
        }
        for bucket in items.values()
    ]
    summary.sort(key=lambda row: row["time"], reverse=True)
    return summary
