import hashlib
import json
import os

from utils.audio_processor import _youtube_id

CACHE_DIR = ".temp/cache"


def source_key(source: str, language: str) -> str:
    """Stable ID for a video/file. Local files are keyed by content, so the same
    recording uploaded twice (any name, any user) reuses the cache."""
    if source.startswith(("http://", "https://")):
        ident = _youtube_id(source) or source
    else:
        h = hashlib.sha1()
        with open(source, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        ident = f"file:{h.hexdigest()}"
    return hashlib.sha1(f"{ident}|{language.lower()}".encode()).hexdigest()[:16]


def _path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def load(key: str) -> dict:
    try:
        with open(_path(key), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(key: str, data: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = _path(key) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _path(key))
