"""
tests/test_config.py — Static validation of GAMES_CFG entries.
"""

import pytest
from syndicate_core.config import GAMES_CFG

REQUIRED_KEYS = {"lottolyzer", "pool", "pick", "b_file", "b_sheet", "thelott_key"}

GAME_ORDER = ["pb", "oz", "sat", "sfl", "mwf"]


@pytest.mark.parametrize("game_key", GAME_ORDER)
def test_required_keys_present(game_key):
    cfg = GAMES_CFG[game_key]
    missing = REQUIRED_KEYS - set(cfg.keys())
    assert not missing, f"[{game_key}] missing keys: {missing}"


@pytest.mark.parametrize("game_key", GAME_ORDER)
def test_pool_is_positive_int(game_key):
    pool = GAMES_CFG[game_key]["pool"]
    assert isinstance(pool, int) and pool > 0, \
        f"[{game_key}] pool must be a positive int, got {pool!r}"


@pytest.mark.parametrize("game_key", GAME_ORDER)
def test_lottolyzer_url_is_nonempty_string(game_key):
    url = GAMES_CFG[game_key]["lottolyzer"]
    assert isinstance(url, str) and url.startswith("https://"), \
        f"[{game_key}] lottolyzer must be an https URL, got {url!r}"


def test_no_two_games_share_lottolyzer_url():
    urls = {gk: cfg["lottolyzer"] for gk, cfg in GAMES_CFG.items()}
    seen: dict[str, str] = {}
    for gk, url in urls.items():
        if url in seen:
            pytest.fail(
                f"Duplicate lottolyzer URL between [{seen[url]}] and [{gk}]: {url}"
            )
        seen[url] = gk
