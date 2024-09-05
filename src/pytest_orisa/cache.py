import pickle
from pathlib import Path

from platformdirs import user_cache_dir

from pytest_orisa.components.result import RunContent

CACHE_VERSION = 1


def get_cache_file() -> Path:
    """
    Returns the path to the cache file on disk
    """
    cache_dir = Path(user_cache_dir(appname="pytest_orisa"))
    cache_file = cache_dir / f"cache-{CACHE_VERSION}.pickle"
    return cache_file


def load_cache():
    """
    Returns a Cache (a list of strings) by loading
    from a pickle saved to disk
    """
    cache_file = get_cache_file()
    try:
        with cache_file.open("rb") as f:
            cache: dict[str, RunContent] = pickle.load(f)
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
    """
    Updates dumps buffer contents to to disk
    """
    cache_file = get_cache_file()
    print(cache_file)
    print(cache_file)
    print(cache_file)
    print(cache_file)
    print(cache_file)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "wb") as f:
        pickle.dump(cache, f)
