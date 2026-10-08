"""Compute what you've watched but not yet rated, plus helpful averages.

Pure functions over Trakt's /sync/watched and /sync/ratings payloads so the GUI
stays dumb and this stays testable. See the __main__ self-check at the bottom.
"""

from collections import defaultdict

# Most-recent-watched caps (user-facing lists). Movies are uncapped.
LIMIT_SHOWS = 10
LIMIT_SEASONS = 20
LIMIT_EPISODES = 50


def _recent(items, limit):
    """Sort by watched-at (ISO strings sort chronologically) newest-first, take
    `limit`, and drop the sort key from each media dict."""
    items.sort(key=lambda m: m.pop("_at", "") or "", reverse=True)
    return items[:limit] if limit else items


def compute(watched_movies, watched_shows, rated_movies, rated_shows,
            rated_seasons, rated_episodes,
            limit_shows=LIMIT_SHOWS, limit_seasons=LIMIT_SEASONS,
            limit_episodes=LIMIT_EPISODES):
    """Return {'movies','shows','seasons','episodes'}: lists of unrated `media`
    dicts ready for the rating UI, episodes/seasons/shows capped to the most
    recently watched. Shows carry 'avg' = mean of your season ratings for that
    show; seasons carry 'avg' = mean of your episode ratings for that season
    (both None when you've rated none yet)."""
    rated_movie = {m["movie"]["ids"]["trakt"] for m in rated_movies}
    rated_show = {s["show"]["ids"]["trakt"] for s in rated_shows}
    rated_season = {(r["show"]["ids"]["trakt"], r["season"]["number"]) for r in rated_seasons}
    rated_ep = {(r["show"]["ids"]["trakt"], r["episode"]["season"], r["episode"]["number"])
                for r in rated_episodes}

    ep_by_season = defaultdict(list)
    for r in rated_episodes:
        ep_by_season[(r["show"]["ids"]["trakt"], r["episode"]["season"])].append(r["rating"])
    season_avg = {k: sum(v) / len(v) for k, v in ep_by_season.items()}

    season_by_show = defaultdict(list)
    for r in rated_seasons:
        season_by_show[r["show"]["ids"]["trakt"]].append(r["rating"])
    show_avg = {k: sum(v) / len(v) for k, v in season_by_show.items()}

    movies = [
        {"kind": "movie", "title": m["movie"]["title"],
         "year": m["movie"].get("year"), "ids": m["movie"]["ids"]}
        for m in watched_movies if m["movie"]["ids"]["trakt"] not in rated_movie
    ]

    shows, seasons, episodes = [], [], []
    for s in watched_shows:
        sh = s["show"]
        sid = sh["ids"]["trakt"]
        if sid not in rated_show:
            shows.append({"kind": "show", "title": sh["title"], "ids": sh["ids"],
                          "avg": show_avg.get(sid), "_at": s.get("last_watched_at")})
        for season in s.get("seasons", []):
            snum = season["number"]
            if (sid, snum) not in rated_season:
                seasons.append({"kind": "season", "title": sh["title"], "ids": sh["ids"],
                                "season": snum, "avg": season_avg.get((sid, snum)),
                                "_at": season.get("last_watched_at")})
            for ep in season.get("episodes", []):
                enum = ep["number"]
                if (sid, snum, enum) not in rated_ep:
                    episodes.append({"kind": "episode", "title": sh["title"], "ids": sh["ids"],
                                     "season": snum, "episode": enum,
                                     "_at": ep.get("last_watched_at")})
    return {
        "movies": movies,
        "shows": _recent(shows, limit_shows),
        "seasons": _recent(seasons, limit_seasons),
        "episodes": _recent(episodes, limit_episodes),
    }


if __name__ == "__main__":
    ids = lambda t: {"trakt": t, "slug": f"s{t}"}
    watched_movies = [{"movie": {"title": "A", "year": 2001, "ids": ids(1)}},
                      {"movie": {"title": "B", "year": 2002, "ids": ids(2)}}]
    watched_shows = [{
        "show": {"title": "Show", "ids": ids(10)},
        "last_watched_at": "2026-01-01T00:00:00Z",
        "seasons": [
            {"number": 1, "last_watched_at": "2026-01-01T00:00:00Z",
             "episodes": [{"number": 1, "last_watched_at": "2026-01-01T00:00:00Z"},
                          {"number": 2, "last_watched_at": "2026-01-02T00:00:00Z"}]},
            {"number": 2, "last_watched_at": "2026-02-01T00:00:00Z",
             "episodes": [{"number": 1, "last_watched_at": "2026-02-01T00:00:00Z"}]},
        ],
    }]
    rated_movies = [{"movie": {"ids": ids(1)}, "rating": 8}]          # movie 1 rated
    rated_shows = []                                                   # show unrated
    rated_seasons = [{"show": {"ids": ids(10)}, "season": {"number": 1}, "rating": 6}]  # S1 rated
    rated_episodes = [{"show": {"ids": ids(10)}, "episode": {"season": 1, "number": 1}, "rating": 10},
                      {"show": {"ids": ids(10)}, "episode": {"season": 1, "number": 2}, "rating": 8}]

    out = compute(watched_movies, watched_shows, rated_movies, rated_shows,
                  rated_seasons, rated_episodes)
    assert [m["title"] for m in out["movies"]] == ["B"], out["movies"]
    assert out["shows"][0]["avg"] == 6.0           # mean of its one rated season
    assert {s["season"] for s in out["seasons"]} == {2}, out["seasons"]   # S1 rated, S2 not
    assert {(e["season"], e["episode"]) for e in out["episodes"]} == {(2, 1)}, out["episodes"]
    assert out["seasons"][0]["avg"] is None        # S2 has no rated episodes
    assert "_at" not in out["episodes"][0]         # sort key stripped

    # recency + caps: 3 unrated episodes across one show, keep newest 2
    many = [{"show": {"title": "X", "ids": ids(99)},
             "last_watched_at": "2026-03-01T00:00:00Z",
             "seasons": [{"number": 1, "last_watched_at": "2026-03-01T00:00:00Z",
                          "episodes": [{"number": n, "last_watched_at": f"2026-03-0{n}T00:00:00Z"}
                                       for n in (1, 2, 3)]}]}]
    out2 = compute([], many, [], [], [], [], limit_episodes=2)
    assert [e["episode"] for e in out2["episodes"]] == [3, 2], out2["episodes"]
    print("ok")
