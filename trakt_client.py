import base64
import hashlib
import secrets
import time
import urllib.parse

import requests

import config

API_BASE = "https://api.trakt.tv"
AUTHORIZE_URL = "https://auth.trakt.tv/oauth/authorize"
# Trakt requires an https redirect URI (no OOB / localhost). This static page
# just displays the ?code= for the user to paste back into potrakt.
REDIRECT_URI = "https://hijast.github.io/potrakt/callback/"


def new_pkce():
    """Return (code_verifier, code_challenge) for a PKCE S256 exchange."""
    verifier = secrets.token_urlsafe(64)[:128]  # URL-safe, within 43-128 chars
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


class TraktClient:
    def __init__(self):
        self.cfg = config.load()

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
        r = requests.post(
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
        r = requests.post(
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
        r = requests.get(f"{API_BASE}/search/movie", params=params, headers=self.headers())
        r.raise_for_status()
        results = r.json()
        return results[0]["movie"] if results else None

    def search_show(self, title):
        r = requests.get(f"{API_BASE}/search/show", params={"query": title}, headers=self.headers())
        r.raise_for_status()
        results = r.json()
        return results[0]["show"] if results else None

    # ---- scrobble ----

    def scrobble(self, action, payload):
        r = requests.post(f"{API_BASE}/scrobble/{action}", json=payload, headers=self.headers())
        r.raise_for_status()
        return r.json()

    # ---- ratings ----

    def rate(self, payload):
        r = requests.post(f"{API_BASE}/sync/ratings", json=payload, headers=self.headers())
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
            r = requests.get(f"{API_BASE}{path}", params=params, headers=self.headers())
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
