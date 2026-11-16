import pytest
from fastapi.testclient import TestClient

from due_diligent.api import app, get_source
from due_diligent.cache import CachedSource
from due_diligent.data import CompanyData


class CountingSource:
    """A fake source that counts how often it's asked, so tests can see cache hits."""
    def __init__(self):
        self.calls = 0

    def get_company(self, ticker: str) -> CompanyData:
        self.calls += 1
        return CompanyData(ticker=ticker, previous_close=100, trailing_eps=5)


class FlakySource:
    """Fails on the first call, works after that."""
    def __init__(self):
        self.calls = 0

    def get_company(self, ticker: str) -> CompanyData:
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("network blip")
        return CompanyData(ticker=ticker, previous_close=100, trailing_eps=5)


class FakeClock:
    """A clock the test moves by hand, instead of sleeping."""
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_second_call_is_served_from_cache():
    inner = CountingSource()
    cache = CachedSource(inner, ttl_seconds=60)
    first = cache.get_company("AAPL")
    second = cache.get_company("AAPL")
    assert inner.calls == 1
    assert second is first


def test_each_ticker_is_cached_separately():
    inner = CountingSource()
    cache = CachedSource(inner, ttl_seconds=60)
    cache.get_company("AAPL")
    cache.get_company("MSFT")
    cache.get_company("AAPL")
    assert inner.calls == 2


def test_entry_expires_after_ttl():
    inner, clock = CountingSource(), FakeClock()
    cache = CachedSource(inner, ttl_seconds=60, clock=clock)
    cache.get_company("AAPL")
    clock.now += 59
    cache.get_company("AAPL")
    assert inner.calls == 1   # still fresh
    clock.now += 2            # 61 s after it was saved
    cache.get_company("AAPL")
    assert inner.calls == 2   # expired, fetched again


def test_errors_are_not_cached():
    inner = FlakySource()
    cache = CachedSource(inner, ttl_seconds=60)
    with pytest.raises(ConnectionError):
        cache.get_company("AAPL")
    assert cache.get_company("AAPL").ticker == "AAPL"   # retried, not stuck on the error
    assert inner.calls == 2


def test_clear_forgets_everything():
    inner = CountingSource()
    cache = CachedSource(inner, ttl_seconds=60)
    cache.get_company("AAPL")
    cache.clear()
    cache.get_company("AAPL")
    assert inner.calls == 2


def test_api_repeat_calls_hit_the_source_once():
    inner = CountingSource()
    cache = CachedSource(inner, ttl_seconds=60)
    app.dependency_overrides[get_source] = lambda: cache
    try:
        client = TestClient(app)
        assert client.get("/tickers/AAPL").status_code == 200
        assert client.get("/tickers/aapl").status_code == 200   # same ticker after uppercasing
        assert inner.calls == 1
    finally:
        app.dependency_overrides.clear()