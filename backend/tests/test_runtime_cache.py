from app.services.runtime_cache import TTLCache


def test_ttl_cache_respects_entry_limit():
    cache = TTLCache()
    cache.set("a", 1, max_entries=1, ttl_seconds=60)
    cache.set("b", 2, max_entries=1, ttl_seconds=60)

    assert cache.get("a", max_entries=1, ttl_seconds=60) is None
    assert cache.get("b", max_entries=1, ttl_seconds=60) == 2


def test_ttl_cache_disabled_by_zero_size():
    cache = TTLCache()
    cache.set("a", 1, max_entries=0, ttl_seconds=60)

    assert cache.get("a", max_entries=1, ttl_seconds=60) is None
