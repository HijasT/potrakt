import json

from paths import app_dir

CONFIG_PATH = app_dir() / "config.json"

DEFAULTS = {
    "client_id": "",
    "client_secret": "",
    "access_token": "",
    "refresh_token": "",
    "expires_at": 0,
    "rate_on_finish": False,
    "shortcuts_created": False,
}


def load():
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return {**DEFAULTS, **data}
    save(dict(DEFAULTS))
    return dict(DEFAULTS)


def save(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
