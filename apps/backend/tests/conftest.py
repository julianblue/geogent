from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from geogent_backend.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
