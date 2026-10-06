import httpx
import pytest
from elevenlabs import ElevenLabs


@pytest.fixture
def mock_client():
    """Return a factory: mock_client(handler) -> (client, requests_seen)."""

    def factory(handler):
        seen: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        client = ElevenLabs(
            api_key="test-key",
            httpx_client=httpx.Client(transport=httpx.MockTransport(recording)),
        )
        return client, seen

    return factory
