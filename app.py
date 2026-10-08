import queue
import secrets
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import autorun
import config
import history
import installer
import ratings
from matcher import identify
from paths import resource_dir
import trakt_client
from potplayer_ctl import get_state
from trakt_client import REDIRECT_URI, TraktClient

ICON_PATH = resource_dir() / "icon.ico"
POLL_INTERVAL_SECONDS = 10

BG = "#1e1f26"
PANEL = "#262834"
FG = "#f2f2f5"
MUTED = "#9a9cad"
ACCENT = "#ed1c24"  # trakt red


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("potrakt")
        self.geometry("560x640")
        self.minsize(480, 420)
        self.configure(bg=BG)
        self.resizable(True, True)
        if ICON_PATH.exists():
            try:
                self.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass

        self.client = TraktClient()
        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        self.current_frame = None
        self.route()

    def route(self):
        if not self.client.has_credentials():
            self.show(SetupFrame)
        elif not self.client.has_token():
            self.show(AuthFrame)
        else:
            self.show(DashboardFrame)

    def show(self, frame_cls):
        if self.current_frame is not None:
            self.current_frame.destroy()
        self.current_frame = frame_cls(self.container, self)
        self.current_frame.pack(fill="both", expand=True)


def heading(parent, text):
    f = tkfont.Font(family="Segoe UI", size=16, weight="bold")
    lbl = tk.Label(parent, text=text, font=f, fg=FG, bg=BG)
    return lbl


def body(parent, text, **kw):
    f = tkfont.Font(family="Segoe UI", size=10)
    lbl = tk.Label(parent, text=text, font=f, fg=MUTED, bg=BG, justify="left", wraplength=460, **kw)
    return lbl


def primary_button(parent, text, command):
    return tk.Button(
        parent, text=text, command=command, bg=ACCENT, fg="white",
        activebackground="#c8171e", activeforeground="white",
        relief="flat", font=("Segoe UI", 10, "bold"), padx=14, pady=8, cursor="hand2",
    )


def secondary_button(parent, text, command):
    return tk.Button(
        parent, text=text, command=command, bg=PANEL, fg=FG,
        activebackground="#33364a", activeforeground=FG,
        relief="flat", font=("Segoe UI", 9), padx=10, pady=6, cursor="hand2",
    )


class SetupFrame(tk.Frame):
    """Step 1: get client_id / client_secret from the user's own Trakt app."""

    def __init__(self, parent, app: App):
        super().__init__(parent, bg=BG, padx=30, pady=24)
        self.app = app

        heading(self, "Connect your Trakt app").pack(anchor="w", pady=(0, 6))
        body(
            self,
            "potrakt checks in what you watch in PotPlayer to your Trakt.tv "
            "profile. First, create a free API app on Trakt (takes ~30 seconds):",
        ).pack(anchor="w", pady=(0, 12))

        steps = tk.Frame(self, bg=BG)
        steps.pack(fill="x", pady=(0, 10))
        secondary_button(steps, "1. Open trakt.tv to create an app", self.open_trakt).pack(
            side="left"
        )
        body(self, "Click the + button there to create a new API app.").pack(anchor="w", pady=(4, 0))

        uri_row = tk.Frame(self, bg=BG)
        uri_row.pack(fill="x", pady=(10, 16))
        body(uri_row, "2. Redirect URI (paste this exactly into the form):").pack(anchor="w")
        uri_box = tk.Entry(uri_row, font=("Consolas", 10), bg=PANEL, fg=FG, relief="flat", insertbackground=FG)
        uri_box.insert(0, REDIRECT_URI)
        uri_box.configure(state="readonly", readonlybackground=PANEL)
        uri_box.pack(fill="x", pady=(4, 0), ipady=4)

        body(self, "3. Paste your Client ID below:").pack(anchor="w", pady=(4, 8))

        self.client_id_var = tk.StringVar()
        self._labeled_entry(self, "Client ID", self.client_id_var)

        self.error_lbl = tk.Label(self, text="", fg="#ff8080", bg=BG, font=("Segoe UI", 9))
        self.error_lbl.pack(anchor="w", pady=(6, 0))

        primary_button(self, "Continue", self.on_continue).pack(anchor="e", pady=(16, 0))

    def _labeled_entry(self, parent, label, var, show=None):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 8))
        tk.Label(row, text=label, fg=MUTED, bg=BG, font=("Segoe UI", 9)).pack(anchor="w")
        entry = tk.Entry(
            row, textvariable=var, font=("Consolas", 10), bg=PANEL, fg=FG,
            relief="flat", insertbackground=FG, show=show or "",
        )
        entry.pack(fill="x", ipady=5)

    def open_trakt(self):
        webbrowser.open("https://developer.trakt.tv/")

    def on_continue(self):
        cid = self.client_id_var.get().strip()
        if not cid:
            self.error_lbl.configure(text="Client ID is required.")
            return
        self.app.client.set_credentials(cid)
        self.app.show(AuthFrame)


class AuthFrame(tk.Frame):
    """Step 2: Trakt authorization via the PKCE flow.

    Opens Trakt's authorize page in the browser; after the user approves, the
    https callback page shows an authorization code they paste back here, which
    we exchange for tokens. No client secret involved.
    """

    def __init__(self, parent, app: App):
        super().__init__(parent, bg=BG, padx=30, pady=24)
        self.app = app
        self.verifier, challenge = trakt_client.new_pkce()
        self.auth_url = app.client.authorize_url(challenge, state=secrets.token_hex(8))

        heading(self, "Authorize with Trakt").pack(anchor="w", pady=(0, 6))
        body(self, "A Trakt page is opening in your browser. Approve potrakt there, "
                   "then copy the authorization code it shows and paste it below.").pack(
            anchor="w", pady=(0, 16))

        secondary_button(self, "Re-open the Trakt authorize page", self.open_auth).pack(anchor="w")

        body(self, "Authorization code:").pack(anchor="w", pady=(16, 4))
        self.code_var = tk.StringVar()
        entry = tk.Entry(self, textvariable=self.code_var, font=("Consolas", 10), bg=PANEL,
                         fg=FG, relief="flat", insertbackground=FG)
        entry.pack(fill="x", ipady=5)

        self.status_lbl = tk.Label(self, text="", fg="#ff8080", bg=BG, font=("Segoe UI", 9))
        self.status_lbl.pack(anchor="w", pady=(6, 0))

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", pady=(16, 0))
        secondary_button(row, "Back", lambda: app.show(SetupFrame)).pack(side="left")
        self.submit_btn = primary_button(row, "Connect", self.submit)
        self.submit_btn.pack(side="right")

        self.after(300, self.open_auth)

    def open_auth(self):
        webbrowser.open(self.auth_url)

    def submit(self):
        code = self.code_var.get().strip()
        if not code:
            self.status_lbl.configure(text="Paste the authorization code first.")
            return
        self.submit_btn.configure(state="disabled")
        self.status_lbl.configure(text="Exchanging code with Trakt...", fg=MUTED)
        threading.Thread(target=self._exchange, args=(code,), daemon=True).start()

    def _exchange(self, code):
        try:
            self.app.client.exchange_code(code, self.verifier)
        except Exception as exc:
            self.after(0, lambda: self._failed(exc))
            return
        self.after(0, lambda: self.app.show(DashboardFrame))

    def _failed(self, exc):
        self.submit_btn.configure(state="normal")
        self.status_lbl.configure(text=f"Couldn't authorize: {exc}", fg="#ff8080")


class DashboardFrame(tk.Frame):
    """Running state: watches PotPlayer and scrobbles to Trakt."""

    def __init__(self, parent, app: App):
        super().__init__(parent, bg=BG, padx=30, pady=24)
        self.app = app
        self.client = app.client
        self.events = queue.Queue()
        self.running = True
        self.worker = None
        self.current_media = None

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x")
        heading(top, "potrakt").pack(side="left")
        secondary_button(top, "Sign out", self.sign_out).pack(side="right")

        status_row = tk.Frame(self, bg=BG)
        status_row.pack(fill="x", pady=(16, 0))
        self.status_dot = tk.Label(status_row, text="●", fg="#5cd65c", bg=BG, font=("Segoe UI", 12))
        self.status_dot.pack(side="left")
        self.status_lbl = tk.Label(
            status_row, text="Watching for PotPlayer...", fg=FG, bg=BG, font=("Segoe UI", 12, "bold")
        )
        self.status_lbl.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(self, length=460, mode="determinate")
        self.progress.pack(pady=(16, 4), anchor="w")

        actions_row = tk.Frame(self, bg=BG)
        actions_row.pack(fill="x", pady=(6, 0))
        secondary_button(actions_row, "View on Trakt", self.view_on_trakt).pack(side="left")
        secondary_button(actions_row, "History", self.open_history).pack(side="left", padx=(8, 0))
        secondary_button(actions_row, "Unrated", self.open_ratings).pack(side="left", padx=(8, 0))
        secondary_button(actions_row, "Create shortcuts", self.create_shortcuts).pack(side="left", padx=(8, 0))

        settings_row = tk.Frame(self, bg=BG)
        settings_row.pack(fill="x", pady=(16, 0))

        self.autorun_var = tk.BooleanVar(value=autorun.is_enabled())
        tk.Checkbutton(
            settings_row, text="Start potrakt when Windows starts", variable=self.autorun_var,
            command=self.toggle_autorun, bg=BG, fg=FG, selectcolor=PANEL,
            activebackground=BG, activeforeground=FG, font=("Segoe UI", 9),
        ).pack(anchor="w")

        self.rate_var = tk.BooleanVar(value=self.client.cfg.get("rate_on_finish", False))
        tk.Checkbutton(
            settings_row, text="Pop up a rating prompt when something finishes", variable=self.rate_var,
            command=self.toggle_rate_on_finish, bg=BG, fg=FG, selectcolor=PANEL,
            activebackground=BG, activeforeground=FG, font=("Segoe UI", 9),
        ).pack(anchor="w")

        tk.Label(self, text="Activity", fg=MUTED, bg=BG, font=("Segoe UI", 9)).pack(anchor="w", pady=(16, 4))
        self.log = tk.Text(
            self, height=10, bg=PANEL, fg=FG, relief="flat", font=("Consolas", 9), state="disabled"
        )
        self.log.pack(fill="both", expand=True)

        app.protocol("WM_DELETE_WINDOW", self.on_close)

        self.start_worker()
        self.after(200, self.pump_events)

        if not self.client.cfg.get("shortcuts_created"):
            self.after(500, lambda: self.create_shortcuts(silent=True))

    def log_line(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {text}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def toggle_autorun(self):
        try:
            if self.autorun_var.get():
                autorun.enable()
            else:
                autorun.disable()
        except OSError as exc:
            messagebox.showerror("potrakt", f"Couldn't update startup setting: {exc}")
            self.autorun_var.set(autorun.is_enabled())

    def toggle_rate_on_finish(self):
        self.client.cfg["rate_on_finish"] = self.rate_var.get()
        config.save(self.client.cfg)

    def view_on_trakt(self):
        url = trakt_url(self.current_media) if self.current_media else None
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("potrakt", "Nothing identified on Trakt yet.")

    def open_history(self):
        HistoryWindow(self.app, self.client)

    def open_ratings(self):
        RatingsWindow(self.app, self.client)

    def create_shortcuts(self, silent=False):
        try:
            installer.create_shortcuts()
            self.client.cfg["shortcuts_created"] = True
            config.save(self.client.cfg)
            if not silent:
                messagebox.showinfo("potrakt", "Desktop and Start Menu shortcuts created.")
            self.log_line("Created Desktop and Start Menu shortcuts.")
        except Exception as exc:
            if not silent:
                messagebox.showerror("potrakt", f"Couldn't create shortcuts: {exc}")

    def sign_out(self):
        self.running = False
        self.client.sign_out()
        self.app.show(AuthFrame)

    def on_close(self):
        self.running = False
        self.app.destroy()

    def start_worker(self):
        self.worker = threading.Thread(target=scrobble_loop, args=(self.client, self.events, self.is_running), daemon=True)
        self.worker.start()

    def is_running(self):
        return self.running

    def pump_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self.log_line(payload)
                elif kind == "status":
                    self.status_lbl.configure(text=payload)
                elif kind == "progress":
                    self.progress["value"] = payload
                elif kind == "playing":
                    self.status_dot.configure(fg="#5cd65c" if payload else MUTED)
                elif kind == "current_media":
                    self.current_media = payload
                elif kind == "rate_prompt":
                    RatingPopup(self.app, self.client, payload["media"])
        except queue.Empty:
            pass
        if self.running:
            self.after(200, self.pump_events)


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


def build_rating_payload(media, rating):
    kind = media["kind"]
    if kind == "movie":
        return {"movies": [{"ids": media["ids"], "rating": rating}]}
    if kind == "show":
        return {"shows": [{"ids": media["ids"], "rating": rating}]}
    if kind == "season":
        return {"shows": [{"ids": media["ids"],
                           "seasons": [{"number": media["season"], "rating": rating}]}]}
    return {
        "shows": [
            {
                "ids": media["ids"],
                "seasons": [
                    {"number": media["season"], "episodes": [{"number": media["episode"], "rating": rating}]}
                ],
            }
        ]
    }


def display_name(media):
    kind = media["kind"]
    if kind == "movie":
        year = f" ({media['year']})" if media.get("year") else ""
        return f"{media['title']}{year}"
    if kind == "show":
        return media["title"]
    if kind == "season":
        return f"{media['title']} — Season {media['season']}"
    return f"{media['title']} S{media['season']:02d}E{media['episode']:02d}"


def trakt_url(media):
    ids = media.get("ids") if media else None
    if not ids:
        return None
    ref = ids.get("slug") or str(ids.get("trakt"))
    kind = media["kind"]
    if kind == "movie":
        return f"https://trakt.tv/movies/{ref}"
    if kind == "show":
        return f"https://trakt.tv/shows/{ref}"
    if kind == "season":
        return f"https://trakt.tv/shows/{ref}/seasons/{media['season']}"
    return f"https://trakt.tv/shows/{ref}/seasons/{media['season']}/episodes/{media['episode']}"


def media_history_fields(media):
    fields = {"kind": media.get("kind"), "title": media.get("title"), "ids": media.get("ids")}
    if media.get("kind") == "episode":
        fields["season"] = media.get("season")
        fields["episode"] = media.get("episode")
    else:
        fields["year"] = media.get("year")
    return fields


def resolve(client, parsed, events):
    try:
        if parsed["kind"] == "movie":
            match = client.search_movie(parsed["title"], parsed.get("year"))
        else:
            match = client.search_show(parsed["title"])
        if match:
            parsed["ids"] = match["ids"]
            events.put(("log", f"Matched '{parsed['title']}' on Trakt"))
            if parsed["kind"] == "episode":
                loc = client.locate_episode(match["ids"]["trakt"], parsed["season"], parsed["episode"])
                if loc != (parsed["season"], parsed["episode"]):
                    events.put(("log", f"Remapped E{parsed['episode']} (absolute) to "
                                       f"S{loc[0]:02d}E{loc[1]:02d}"))
                    parsed["season"], parsed["episode"] = loc
        else:
            events.put(("log", f"No Trakt match for '{parsed['title']}' - will scrobble by title"))
    except Exception as exc:
        events.put(("log", f"Search failed, scrobbling by title only: {exc}"))
    return parsed


def finish_current(client, events, filename, media, progress):
    client.scrobble("stop", build_payload(media, progress))
    events.put(("log", f"Stopped: {filename} at {progress:.0f}%"))
    history.log_event("stop", filename=filename, progress=progress, **media_history_fields(media))
    events.put(("current_media", None))
    if progress >= 80 and media.get("ids") and client.cfg.get("rate_on_finish"):
        events.put(("rate_prompt", {"media": media}))


def scrobble_loop(client, events, is_running):
    current_file = None
    current_media = None
    last_progress = 0.0
    last_playing = None

    while is_running():
        try:
            client.ensure_token()
            state = get_state()

            if state is None:
                if current_file:
                    finish_current(client, events, current_file, current_media, last_progress)
                    current_file, current_media = None, None
                    events.put(("status", "Watching for PotPlayer..."))
                    events.put(("progress", 0))
                    events.put(("playing", False))
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            progress = 0.0
            if state["total_ms"] > 0:
                progress = min(100.0, state["current_ms"] / state["total_ms"] * 100)

            if state["filename"] != current_file:
                if current_file:
                    finish_current(client, events, current_file, current_media, last_progress)
                    current_file, current_media = None, None

                parsed = identify(state["filename"])
                if parsed is None:
                    events.put(("log", f"Could not identify: {state['filename']}"))
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue

                events.put(("status", f"Identifying {state['filename']}..."))
                parsed = resolve(client, parsed, events)
                current_file = state["filename"]
                current_media = parsed
                last_playing = state["playing"]

                action = "start" if state["playing"] else "pause"
                client.scrobble(action, build_payload(current_media, progress))
                events.put(("log", f"{action.capitalize()}: {display_name(current_media)} ({progress:.0f}%)"))
                history.log_event(action, filename=current_file, progress=progress, **media_history_fields(current_media))
                events.put(("status", display_name(current_media)))
                events.put(("current_media", current_media))

            elif state["playing"] != last_playing:
                action = "start" if state["playing"] else "pause"
                client.scrobble(action, build_payload(current_media, progress))
                events.put(("log", f"{action.capitalize()}: {display_name(current_media)} ({progress:.0f}%)"))
                history.log_event(action, filename=current_file, progress=progress, **media_history_fields(current_media))
                last_playing = state["playing"]

            events.put(("progress", progress))
            events.put(("playing", state["playing"]))
            last_progress = progress
            time.sleep(POLL_INTERVAL_SECONDS)

        except Exception as exc:
            events.put(("log", f"Error: {exc}"))
            time.sleep(POLL_INTERVAL_SECONDS)

    if current_file:
        try:
            client.scrobble("stop", build_payload(current_media, last_progress))
        except Exception:
            pass


class RatingPopup(tk.Toplevel):
    """Small popup offering a 1-10 rating for something that just finished."""

    def __init__(self, parent, client, media, on_rated=None):
        super().__init__(parent)
        self.client = client
        self.media = media
        self.on_rated = on_rated

        self.title("Rate it")
        self.configure(bg=BG)
        self.geometry("380x170")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        tk.Label(
            self, text=f"How was:\n{display_name(media)}?", bg=BG, fg=FG,
            font=("Segoe UI", 11, "bold"), justify="center",
        ).pack(pady=(18, 10))

        btns = tk.Frame(self, bg=BG)
        btns.pack()
        for n in range(1, 11):
            tk.Button(
                btns, text=str(n), width=2, command=lambda n=n: self.rate(n),
                bg=PANEL, fg=FG, relief="flat", activebackground=ACCENT, activeforeground="white",
            ).grid(row=0, column=n - 1, padx=1)

        secondary_button(self, "Skip", self.destroy).pack(pady=(14, 0))
        self._auto_close = self.after(45000, self._safe_destroy)

    def _safe_destroy(self):
        try:
            self.destroy()
        except tk.TclError:
            pass

    def rate(self, n):
        try:
            self.after_cancel(self._auto_close)
        except Exception:
            pass
        try:
            self.client.rate(build_rating_payload(self.media, n))
            history.log_event("rated", rating=n, **media_history_fields(self.media))
            if self.on_rated:
                self.on_rated(n)
        except Exception as exc:
            messagebox.showerror("potrakt", f"Couldn't submit rating: {exc}")
        self.destroy()


class HistoryWindow(tk.Toplevel):
    """Lists everything potrakt has tracked, with per-item rating + Trakt links."""

    def __init__(self, parent, client):
        super().__init__(parent)
        self.client = client
        self.title("potrakt - History")
        self.geometry("640x480")
        self.configure(bg=BG)

        heading(self, "History").pack(anchor="w", padx=16, pady=(16, 8))

        body_frame = tk.Frame(self, bg=BG)
        body_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        canvas = tk.Canvas(body_frame, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body_frame, orient="vertical", command=canvas.yview)
        self.rows_frame = tk.Frame(canvas, bg=BG)
        self.rows_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.populate()

    def populate(self):
        for child in self.rows_frame.winfo_children():
            child.destroy()

        rows = history.load_summary()
        if not rows:
            tk.Label(self.rows_frame, text="Nothing tracked yet.", fg=MUTED, bg=BG, font=("Segoe UI", 10)).pack(
                anchor="w", pady=8
            )
            return

        for item in rows:
            self._build_row(item)

    def _build_row(self, item):
        media = item["media"]
        row = tk.Frame(self.rows_frame, bg=PANEL)
        row.pack(fill="x", pady=3)

        info = tk.Frame(row, bg=PANEL)
        info.pack(side="left", fill="x", expand=True, padx=(10, 4), pady=8)

        tk.Label(info, text=display_name(media), fg=FG, bg=PANEL, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        rating_text = f"Rated {item['rating']}/10" if item["rating"] else "Not rated"
        sub = f"{item['time']}  ·  {item['progress']:.0f}% watched  ·  {rating_text}"
        tk.Label(info, text=sub, fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w")

        actions = tk.Frame(row, bg=PANEL)
        actions.pack(side="right", padx=10, pady=8)

        rate_btn = secondary_button(actions, "Rate", lambda: self.open_rate(item))
        rate_btn.pack(side="left", padx=(0, 6))
        if not media.get("ids"):
            rate_btn.configure(state="disabled")

        trakt_btn = secondary_button(actions, "View on Trakt", lambda: self.open_trakt(item))
        trakt_btn.pack(side="left")
        if not media.get("ids"):
            trakt_btn.configure(state="disabled")

    def open_rate(self, item):
        RatingPopup(self, self.client, item["media"], on_rated=lambda n: self.populate())

    def open_trakt(self, item):
        url = trakt_url(item["media"])
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("potrakt", "No Trakt match for this item.")


def _scroll_frame(parent):
    """A vertically scrollable frame; returns the inner frame to pack rows into."""
    canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=BG)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    return inner


# (tab key, label, sublabel prefix for the per-item average — None = no average)
RATING_TABS = [
    ("episodes", "Episodes", None),
    ("seasons", "Seasons", "avg episode rating"),
    ("shows", "Shows", "avg season rating"),
    ("movies", "Movies", None),
]


class RatingsWindow(tk.Toplevel):
    """Watched-but-unrated items (from Trakt), in tabs, with inline rating."""

    def __init__(self, parent, client):
        super().__init__(parent)
        self.client = client
        self.data = {}
        self.title("potrakt - Unrated")
        self.geometry("680x540")
        self.configure(bg=BG)

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(16, 8))
        heading(top, "Unrated").pack(side="left")
        self.refresh_btn = secondary_button(top, "Refresh", self.load)
        self.refresh_btn.pack(side="right")

        self.status = tk.Label(self, text="", fg=MUTED, bg=BG, font=("Segoe UI", 9))
        self.status.pack(anchor="w", padx=16)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        self.tabs = {}  # key -> (tab frame, inner rows frame)
        for key, label, _ in RATING_TABS:
            tab = tk.Frame(self.notebook, bg=BG)
            self.notebook.add(tab, text=label)
            self.tabs[key] = (tab, _scroll_frame(tab))

        self.load()

    def load(self):
        self.refresh_btn.configure(state="disabled")
        self.status.configure(text="Loading your watched + rated history from Trakt...", fg=MUTED)
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            self.client.ensure_token()
            data = ratings.compute(
                self.client.watched_movies(),
                self.client.watched_shows(),
                self.client.ratings("movies"),
                self.client.ratings("shows"),
                self.client.ratings("seasons"),
                self.client.ratings("episodes"),
            )
        except Exception as exc:
            self.after(0, lambda: self._failed(exc))
            return
        self.after(0, lambda: self._loaded(data))

    def _failed(self, exc):
        self.refresh_btn.configure(state="normal")
        self.status.configure(text=f"Couldn't load from Trakt: {exc}", fg="#ff8080")

    def _loaded(self, data):
        self.data = data
        self.refresh_btn.configure(state="normal")
        self.status.configure(text="Showing the most recent unrated items you've watched.", fg=MUTED)
        for key, _, _ in RATING_TABS:
            self._populate(key)

    def _populate(self, key):
        _, label, avg_prefix = next(t for t in RATING_TABS if t[0] == key)
        tab, inner = self.tabs[key]
        for child in inner.winfo_children():
            child.destroy()

        items = self.data.get(key, [])
        self.notebook.tab(tab, text=f"{label} ({len(items)})")
        if not items:
            tk.Label(inner, text="Nothing unrated here — nice.", fg=MUTED, bg=BG,
                     font=("Segoe UI", 10)).pack(anchor="w", pady=8)
            return
        for media in items:
            self._build_row(key, inner, media, avg_prefix)

    def _build_row(self, key, parent, media, avg_prefix):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=3, padx=(0, 4))

        info = tk.Frame(row, bg=PANEL)
        info.pack(side="left", fill="x", expand=True, padx=(10, 4), pady=8)
        tk.Label(info, text=display_name(media), fg=FG, bg=PANEL,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        if avg_prefix:
            avg = media.get("avg")
            sub = f"{avg_prefix}: {avg:.1f}/10" if avg is not None else f"{avg_prefix}: none yet"
            tk.Label(info, text=sub, fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w")

        actions = tk.Frame(row, bg=PANEL)
        actions.pack(side="right", padx=10, pady=8)
        secondary_button(actions, "Rate", lambda: self._rate(key, media)).pack(side="left", padx=(0, 6))
        secondary_button(actions, "View on Trakt",
                         lambda: webbrowser.open(trakt_url(media))).pack(side="left")

    def _rate(self, key, media):
        RatingPopup(self, self.client, media, on_rated=lambda n: self._rated(key, media))

    def _rated(self, key, media):
        # It's rated now, so drop it from the unrated list and repaint that tab.
        self.data[key] = [m for m in self.data.get(key, []) if m is not media]
        self._populate(key)


if __name__ == "__main__":
    app = App()
    if "--minimized" in sys.argv:
        app.iconify()
    app.mainloop()
