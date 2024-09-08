import pickle
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

CACHE_VERSION = 1


def get_cache_file() -> Path:
    cache_dir = Path(user_cache_dir(appname="pytest_orisa"))
    cache_file = cache_dir / f"cache-{CACHE_VERSION}.pickle"
    return cache_file


def load_cache() -> Any | None:
    cache_file = get_cache_file()
    try:
        with cache_file.open("rb") as f:
            cache = pickle.load(f)
    except (
        pickle.UnpicklingError,
        ValueError,
        IndexError,
        FileNotFoundError,
        AssertionError,
    ):
        return None
    else:
        return cache


def write_cache(cache) -> None:
    cache_file = get_cache_file()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "wb") as f:
        pickle.dump(cache, f)
