import secrets
import time
import webbrowser

import trakt_client
from matcher import identify
from potplayer_ctl import get_state
from trakt_client import TraktClient

POLL_INTERVAL_SECONDS = 10


def cli_authorize(client):
    """PKCE auth for the headless runner: open the authorize page, paste the code."""
    verifier, challenge = trakt_client.new_pkce()
    url = client.authorize_url(challenge, state=secrets.token_hex(8))
    print(f"\nAuthorize potrakt here (opening in your browser):\n{url}\n")
    webbrowser.open(url)
    code = input("Paste the authorization code shown after approving: ").strip()
    client.exchange_code(code, verifier)
    print("Authenticated with Trakt.\n")


def build_payload(media, progress):
    payload = {"progress": progress}
    if media["kind"] == "movie":
        if media.get("ids"):
            payload["movie"] = {"ids": media["ids"]}
        else:
            payload["movie"] = {"title": media["title"], "year": media.get("year")}
    else:
        if media.get("ids"):
            payload["show"] = {"ids": media["ids"]}
        else:
            payload["show"] = {"title": media["title"]}
        payload["episode"] = {"season": media["season"], "number": media["episode"]}
    return payload


def resolve(client, parsed):
    try:
        if parsed["kind"] == "movie":
            match = client.search_movie(parsed["title"], parsed.get("year"))
        else:
            match = client.search_show(parsed["title"])
        if match:
            parsed["ids"] = match["ids"]
    except Exception as exc:
        print(f"  (search failed, will scrobble by title: {exc})")
    return parsed


def main():
    client = TraktClient()
    if not client.has_credentials():
        print(
            "config.json is missing client_id. Create an app at "
            "https://developer.trakt.tv (redirect uri: "
            f"{trakt_client.REDIRECT_URI}) and fill in config.json, then rerun.\n"
            "Or run 'python app.py' for a guided setup window."
        )
        return
    if not client.has_token():
        cli_authorize(client)
    client.ensure_token()

    current_file = None
    current_media = None
    last_progress = 0.0
    last_playing = None

    print("potrakt running. Watching for PotPlayer playback... (Ctrl+C to stop)")

    try:
        while True:
            client.ensure_token()
            state = get_state()

            if state is None:
                if current_file:
                    client.scrobble("stop", build_payload(current_media, last_progress))
                    print(f"Stopped: {current_file} at {last_progress:.0f}%")
                    current_file, current_media = None, None
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            progress = 0.0
            if state["total_ms"] > 0:
                progress = min(100.0, state["current_ms"] / state["total_ms"] * 100)

            if state["filename"] != current_file:
                if current_file:
                    client.scrobble("stop", build_payload(current_media, last_progress))
                    print(f"Stopped: {current_file} at {last_progress:.0f}%")
                    current_file, current_media = None, None

                parsed = identify(state["filename"])
                if parsed is None:
                    print(f"Could not identify: {state['filename']}")
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue

                parsed = resolve(client, parsed)
                current_file = state["filename"]
                current_media = parsed
                last_playing = state["playing"]

                action = "start" if state["playing"] else "pause"
                client.scrobble(action, build_payload(current_media, progress))
                print(f"{action.capitalize()}: {current_file} ({progress:.0f}%)")

            elif state["playing"] != last_playing:
                action = "start" if state["playing"] else "pause"
                client.scrobble(action, build_payload(current_media, progress))
                print(f"{action.capitalize()}: {current_file} ({progress:.0f}%)")
                last_playing = state["playing"]

            last_progress = progress
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        if current_file:
            client.scrobble("stop", build_payload(current_media, last_progress))
            print(f"Stopped: {current_file} at {last_progress:.0f}%")
        print("potrakt stopped.")


if __name__ == "__main__":
    main()
