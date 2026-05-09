from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from time import monotonic
from typing import Any, Hashable


class TTLCache:
    def __init__(self) -> None:
        self._items: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = RLock()

    def get(self, key: Hashable, max_entries: int, ttl_seconds: int) -> Any | None:
        if max_entries <= 0 or ttl_seconds <= 0:
            return None
        now = monotonic()
        with self._lock:
            record = self._items.get(key)
            if record is None:
                return None
            expires_at, value = record
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: Hashable, value: Any, max_entries: int, ttl_seconds: int) -> None:
        if max_entries <= 0 or ttl_seconds <= 0:
            return
        now = monotonic()
        with self._lock:
            self._evict_expired(now)
            self._items[key] = (now + ttl_seconds, value)
            self._items.move_to_end(key)
            while len(self._items) > max_entries:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def _evict_expired(self, now: float) -> None:
        expired = [key for key, (expires_at, _) in self._items.items() if expires_at <= now]
        for key in expired:
            self._items.pop(key, None)


SEARCH_RESULT_CACHE = TTLCache()
QUERY_EMBEDDING_CACHE = TTLCache()
FOLDER_LIST_CACHE = TTLCache()
IMPORT_STATUS_CACHE = TTLCache()


def clear_runtime_caches() -> None:
    SEARCH_RESULT_CACHE.clear()
    QUERY_EMBEDDING_CACHE.clear()
    FOLDER_LIST_CACHE.clear()
    IMPORT_STATUS_CACHE.clear()
