from guessit import guessit


def identify(filename):
    """Parse a filename into movie/episode info Trakt can search for."""
    info = guessit(filename)
    title = info.get("title")
    if not title:
        return None

    kind = info.get("type")
    if kind == "episode" and "season" in info and "episode" in info:
        season = info["season"]
        episode = info["episode"]
        if isinstance(season, list):
            season = season[0]
        if isinstance(episode, list):
            episode = episode[0]
        return {
            "kind": "episode",
            "title": title,
            "season": season,
            "episode": episode,
        }

    return {
        "kind": "movie",
        "title": title,
        "year": info.get("year"),
    }
