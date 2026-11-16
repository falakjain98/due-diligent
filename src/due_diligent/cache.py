"""An in-memory cache in front of any DataSource, so repeat lookups skip the network."""
from __future__ import annotations

import logging
import time
from typing import Callable

from due_diligent.data import CompanyData, DataSource

logger = logging.getLogger(__name__)


class CachedSource:
    """Wraps another DataSource and remembers each company for ttl_seconds.

    It has the same get_company method as any DataSource, so code that takes a
    DataSource (the API, cli.run) can use it without knowing it's a cache.
    """

    def __init__(self, inner: DataSource, ttl_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._inner = inner
        self._ttl = ttl_seconds
        self._clock = clock  # injectable so tests can move time forward without sleeping
        self._entries: dict[str, tuple[float, CompanyData]] = {}  # ticker -> (saved_at, data)

    def get_company(self, ticker: str) -> CompanyData:
        entry = self._entries.get(ticker)
        if entry is not None:
            saved_at, company = entry
            if self._clock() - saved_at < self._ttl:
                logger.debug("Cache hit for %s", ticker)
                return company
            logger.debug("Cache expired for %s", ticker)
        # Miss or expired: ask the real source. If it raises, nothing is saved,
        # so a network blip isn't remembered as the answer for the next hour.
        company = self._inner.get_company(ticker)
        self._entries[ticker] = (self._clock(), company)
        logger.debug("Cached %s", ticker)
        return company

    def clear(self) -> None:
        """Forget everything (handy in tests, or after a known data correction)."""
        self._entries.clear()