import base64
import hashlib
import secrets
import time
import urllib.parse

import requests

import config

API_BASE = "https://api.trakt.tv"
AUTHORIZE_URL = "https://auth.trakt.tv/oauth/authorize"
# Trakt's Cloudflare rejects the default python-requests user-agent (403, CF
# error 1010), so every request must send a real one.
USER_AGENT = "potrakt/1.0 (+https://github.com/HijasT/potrakt)"
# Trakt requires an https redirect URI (no OOB / localhost). This static page
# just displays the ?code= for the user to paste back into potrakt.
REDIRECT_URI = "https://hijast.github.io/potrakt/callback/"


def pick_episode_location(by_sn, by_abs, season, number):
    """Map a guessed (season, number) to the real Trakt one. Release groups
    often label anime with a season but an absolute episode number (e.g. Black
    Clover 'S3 E140'), which Trakt stores under a different season/number. Prefer
    an exact season+number hit, else fall back to the absolute-number match."""
    if (season, number) in by_sn:
        return season, number
    if number in by_abs:
        return by_abs[number]
    return season, number


def new_pkce():
    """Return (code_verifier, code_challenge) for a PKCE S256 exchange."""
    verifier = secrets.token_urlsafe(64)[:128]  # URL-safe, within 43-128 chars
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


class TraktClient:
    def __init__(self):
        self.cfg = config.load()
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def has_credentials(self):
        # Trakt no longer issues a client_secret; PKCE signs users in with the
        # client_id alone (see the auth flow below).
        return bool(self.cfg["client_id"])

    def has_token(self):
        return bool(self.cfg.get("access_token"))

    def set_credentials(self, client_id):
        self.cfg["client_id"] = client_id.strip()
        config.save(self.cfg)

    def sign_out(self):
        self.cfg["access_token"] = ""
        self.cfg["refresh_token"] = ""
        self.cfg["expires_at"] = 0
        config.save(self.cfg)

    def headers(self):
        return {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self.cfg["client_id"],
            "Authorization": f"Bearer {self.cfg['access_token']}",
        }

    # ---- auth ----

    def ensure_token(self):
        # No interactive auth here: the GUI/CLI drives the PKCE flow explicitly.
        if self.cfg.get("access_token") and time.time() > self.cfg.get("expires_at", 0) - 60:
            self._refresh()

    def authorize_url(self, code_challenge, state):
        """The URL to send the user to; they approve and get an authorization
        code back via the redirect page."""
        q = urllib.parse.urlencode({
            "response_type": "code",
            "client_id": self.cfg["client_id"],
            "redirect_uri": REDIRECT_URI,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        })
        return f"{AUTHORIZE_URL}?{q}"

    def exchange_code(self, code, code_verifier):
        """Trade the pasted authorization code for tokens (PKCE, no secret)."""
        r = self.session.post(
            f"{API_BASE}/oauth/token",
            json={
                "code": code.strip(),
                "client_id": self.cfg["client_id"],
                "redirect_uri": REDIRECT_URI,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
            },
        )
        r.raise_for_status()
        self._store_token(r.json())

    def _refresh(self):
        r = self.session.post(
            f"{API_BASE}/oauth/token",
            json={
                "refresh_token": self.cfg["refresh_token"],
                "client_id": self.cfg["client_id"],
                "redirect_uri": REDIRECT_URI,
                "grant_type": "refresh_token",
            },
        )
        r.raise_for_status()
        self._store_token(r.json())

    def _store_token(self, tok):
        self.cfg["access_token"] = tok["access_token"]
        self.cfg["refresh_token"] = tok.get("refresh_token", "")
        self.cfg["expires_at"] = time.time() + tok.get("expires_in", 0)
        config.save(self.cfg)

    # ---- search ----

    def search_movie(self, title, year=None):
        params = {"query": title}
        if year:
            params["years"] = str(year)
        r = self.session.get(f"{API_BASE}/search/movie", params=params, headers=self.headers())
        r.raise_for_status()
        results = r.json()
        return results[0]["movie"] if results else None

    def search_show(self, title):
        r = self.session.get(f"{API_BASE}/search/show", params={"query": title}, headers=self.headers())
        r.raise_for_status()
        results = r.json()
        return results[0]["show"] if results else None

    # ---- scrobble ----

    def scrobble(self, action, payload):
        r = self.session.post(f"{API_BASE}/scrobble/{action}", json=payload, headers=self.headers())
        if r.status_code == 404:
            raise RuntimeError(
                "Trakt couldn't match this title/episode (404) - the filename guess "
                "was probably wrong, so there's nothing to scrobble"
            )
        r.raise_for_status()
        return r.json()

    # ---- ratings ----

    def rate(self, payload):
        r = self.session.post(f"{API_BASE}/sync/ratings", json=payload, headers=self.headers())
        r.raise_for_status()
        return r.json()

    # ---- watched / unrated ----

    def _get_paged(self, path, params=None):
        """GET every page of a paginated endpoint. Trakt enforced pagination on
        the watched endpoints in 2026 (100/page with extended=progress), so a
        single GET only returns the first page now."""
        params = dict(params or {})
        params["limit"] = 100
        page, out = 1, []
        while True:
            params["page"] = page
            r = self.session.get(f"{API_BASE}{path}", params=params, headers=self.headers())
            r.raise_for_status()
            out.extend(r.json())
            total = int(r.headers.get("X-Pagination-Page-Count") or 1)
            if page >= total:
                return out
            page += 1

    def watched_movies(self):
        return self._get_paged("/sync/watched/movies")

    def watched_shows(self):
        # extended=progress is required now to get the season/episode breakdown;
        # the new default omits it.
        return self._get_paged("/sync/watched/shows", {"extended": "full,progress"})

    def ratings(self, media_type):
        """media_type in {movies, shows, seasons, episodes}."""
        return self._get_paged(f"/sync/ratings/{media_type}")

    # ---- episode location (anime absolute-numbering fix) ----

    def _episode_index(self, show_id):
        """(by_sn, by_abs) for a show, cached per client. by_sn maps
        (season, number)->itself; by_abs maps absolute number->(season, number)."""
        cache = self.__dict__.setdefault("_ep_cache", {})
        if show_id not in cache:
            r = self.session.get(
                f"{API_BASE}/shows/{show_id}/seasons",
                params={"extended": "episodes,full"}, headers=self.headers(),
            )
            r.raise_for_status()
            by_sn, by_abs = {}, {}
            for s in r.json():
                for ep in s.get("episodes", []):
                    loc = (s["number"], ep["number"])
                    by_sn[loc] = loc
                    if ep.get("number_abs") is not None:
                        by_abs[ep["number_abs"]] = loc
            cache[show_id] = (by_sn, by_abs)
        return cache[show_id]

    def locate_episode(self, show_id, season, number):
        """Best (season, number) to scrobble; falls back to the input on error."""
        try:
            by_sn, by_abs = self._episode_index(show_id)
        except Exception:
            return season, number
        return pick_episode_location(by_sn, by_abs, season, number)
