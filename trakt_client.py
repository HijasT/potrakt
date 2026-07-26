import time

import requests

import config

API_BASE = "https://api.trakt.tv"


class AuthPending(Exception):
    """Raised by poll_device_token while the user hasn't authorized yet."""


class AuthDenied(Exception):
    """Raised by poll_device_token if the user denied or the code expired."""


class TraktClient:
    def __init__(self):
        self.cfg = config.load()

    def has_credentials(self):
        return bool(self.cfg["client_id"] and self.cfg["client_secret"])

    def has_token(self):
        return bool(self.cfg.get("access_token"))

    def set_credentials(self, client_id, client_secret):
        self.cfg["client_id"] = client_id.strip()
        self.cfg["client_secret"] = client_secret.strip()
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
        if not self.cfg.get("access_token"):
            self._device_auth()
        elif time.time() > self.cfg.get("expires_at", 0) - 60:
            self._refresh()

    def request_device_code(self):
        """Step 1 of device auth: get a user_code + verification_url to show."""
        r = requests.post(
            f"{API_BASE}/oauth/device/code",
            json={"client_id": self.cfg["client_id"]},
        )
        r.raise_for_status()
        return r.json()

    def poll_device_token(self, device_code):
        """Step 2, call repeatedly (every `interval` seconds) until it returns True.

        Raises AuthPending while waiting, AuthDenied if expired/denied, or
        re-raises HTTP errors for anything else (e.g. bad credentials).
        """
        resp = requests.post(
            f"{API_BASE}/oauth/device/token",
            json={
                "code": device_code,
                "client_id": self.cfg["client_id"],
                "client_secret": self.cfg["client_secret"],
            },
        )
        if resp.status_code == 200:
            self._store_token(resp.json())
            return True
        if resp.status_code == 400:
            raise AuthPending()
        if resp.status_code == 429:
            raise AuthPending()
        if resp.status_code in (404, 409, 410, 418):
            raise AuthDenied(resp.json().get("error_description", "authorization denied"))
        resp.raise_for_status()
        return False

    def _device_auth(self):
        """Blocking CLI-friendly device auth flow (used by main.py)."""
        data = self.request_device_code()
        print(f"\nGo to {data['verification_url']} and enter code: {data['user_code']}\n")

        interval = data["interval"]
        deadline = time.time() + data["expires_in"]

        while time.time() < deadline:
            time.sleep(interval)
            try:
                if self.poll_device_token(data["device_code"]):
                    print("Authenticated with Trakt.\n")
                    return
            except AuthPending:
                continue

        raise RuntimeError("Trakt device authorization timed out.")

    def _refresh(self):
        r = requests.post(
            f"{API_BASE}/oauth/token",
            json={
                "refresh_token": self.cfg["refresh_token"],
                "client_id": self.cfg["client_id"],
                "client_secret": self.cfg["client_secret"],
                "grant_type": "refresh_token",
            },
        )
        r.raise_for_status()
        self._store_token(r.json())

    def _store_token(self, tok):
        self.cfg["access_token"] = tok["access_token"]
        self.cfg["refresh_token"] = tok["refresh_token"]
        self.cfg["expires_at"] = time.time() + tok["expires_in"]
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
