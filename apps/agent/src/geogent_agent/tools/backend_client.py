import httpx

from geogent_agent.config import get_settings


def get_backend_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(base_url=settings.backend_url, timeout=30.0)
