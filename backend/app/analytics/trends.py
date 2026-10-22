from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def bucket(at, grouping, zone):
    day = datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(zone).date()
    if grouping == "weekly":
        day -= timedelta(days=day.weekday())
    elif grouping == "monthly":
        day = day.replace(day=1)
    return day.isoformat()


def series(rows, start, end, timezone, grouping):
    zone = ZoneInfo(timezone)
    counts = Counter(bucket(row["created_at"], grouping, zone) for row in rows)
    categories = defaultdict(Counter)
    for row in rows:
        categories[bucket(row["created_at"], grouping, zone)][row["category"]] += 1
    keys = set()
    day = start
    while day < end:
        keys.add(bucket(day.isoformat(), grouping, zone))
        day += timedelta(days=1)
    return [
        {"date": key, "count": counts[key], "categories": dict(categories[key])}
        for key in sorted(keys)
    ]
