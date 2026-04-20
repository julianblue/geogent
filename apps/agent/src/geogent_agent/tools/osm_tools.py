import httpx
from langchain_core.tools import tool

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "geogent-agent/0.1 (https://github.com/julianblue/geogent)"


@tool
async def geocode_place(query: str) -> dict:
    """Geocode a free-form place name via OpenStreetMap Nominatim.

    Returns {"lat": float, "lon": float, "display_name": str} for the top match,
    or {"error": str} if nothing was found.
    """
    async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT}) as client:
        r = await client.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
        )
        r.raise_for_status()
        hits = r.json()

    if not hits:
        return {"error": f"No results for {query!r}"}

    top = hits[0]
    return {
        "lat": float(top["lat"]),
        "lon": float(top["lon"]),
        "display_name": top["display_name"],
    }
