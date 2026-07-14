"""Unit tests for NvidiaEmbeddingWrapper: TLS verification stays enabled and
the input_type is forwarded to the NVIDIA payload."""
import pytest

from src.clients import NvidiaEmbeddingWrapper


class _FakeResp:
    def __init__(self, captured):
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}


class _FakeSession:
    """Captures how ClientSession was constructed and what was POSTed."""
    def __init__(self, captured, *args, **kwargs):
        self._captured = captured
        captured["session_args"] = args
        captured["session_kwargs"] = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None):
        self._captured["url"] = url
        self._captured["json"] = json
        return _FakeResp(self._captured)


class _FakeConnector:
    """Captures the ssl argument passed to aiohttp.TCPConnector."""
    def __init__(self, captured, *args, **kwargs):
        captured["connector_kwargs"] = kwargs


@pytest.fixture
def wrapper(monkeypatch):
    monkeypatch.setenv("NVIDIA_EMBEDDING_API_KEY", "test-key")
    return NvidiaEmbeddingWrapper()


@pytest.fixture
def captured(monkeypatch):
    """embed() does a local `import aiohttp`, so patching aiohttp.ClientSession on
    the module object is seen by the function (same module instance)."""
    import aiohttp
    cap = {}
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: _FakeSession(cap, *a, **k))
    monkeypatch.setattr(aiohttp, "TCPConnector", lambda *a, **k: _FakeConnector(cap, *a, **k))
    return cap


@pytest.mark.asyncio
async def test_tls_verification_enabled(wrapper, captured):
    """embed() must use a TLS-verifying SSL context (CERT_REQUIRED), never disable it."""
    import ssl
    await wrapper.embed("some passage", input_type="passage")

    ssl_ctx = captured["connector_kwargs"].get("ssl")
    assert isinstance(ssl_ctx, ssl.SSLContext), "no SSL context passed to the connector"
    assert ssl_ctx.verify_mode == ssl.CERT_REQUIRED
    assert ssl_ctx.check_hostname is True
    # The old insecure switch must be gone.
    assert captured["connector_kwargs"].get("verify_ssl") is not False


@pytest.mark.asyncio
async def test_input_type_defaults_to_query(wrapper, captured):
    await wrapper.embed("a search query")
    assert captured["json"]["input_type"] == "query"


@pytest.mark.asyncio
async def test_input_type_passage_forwarded(wrapper, captured):
    await wrapper.embed("stored content", input_type="passage")
    assert captured["json"]["input_type"] == "passage"
    assert captured["json"]["model"] == "nvidia/nv-embedqa-e5-v5"
