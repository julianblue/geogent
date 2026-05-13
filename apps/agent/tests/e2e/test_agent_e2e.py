"""Live e2e tests that drive the LangGraph dev server with OpenRouter.

Each test makes one chat turn and asserts that the agent (a) invoked the right
backend or external tool and (b) produced a coherent final message. Skipped
unless ``OPENROUTER_API_KEY`` is set in the environment.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph_sdk import get_client

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


def _tool_names_from_state(state: dict[str, Any]) -> list[str]:
    """Collect every tool name the agent invoked during a thread."""
    names: list[str] = []
    for message in state.get("values", {}).get("messages", []):
        if not isinstance(message, dict):
            continue
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict) and "name" in call:
                names.append(call["name"])
    return names


def _final_assistant_text(state: dict[str, Any]) -> str:
    for message in reversed(state.get("values", {}).get("messages", [])):
        if not isinstance(message, dict):
            continue
        if message.get("type") != "ai":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            joined = "".join(parts).strip()
            if joined:
                return joined
    return ""


async def _run_one_turn(
    base_url: str,
    user_message: str,
    *,
    configurable: dict[str, Any] | None = None,
) -> dict[str, Any]:
    client = get_client(url=base_url)
    thread = await client.threads.create()
    await client.runs.wait(
        thread["thread_id"],
        "geogent",
        input={"messages": [{"role": "user", "content": user_message}]},
        config={"configurable": configurable or {}},
    )
    return await client.threads.get_state(thread["thread_id"])


async def test_geocode_then_fly_to_paris(langgraph_server: str) -> None:
    """The agent should geocode Paris and emit a fly_to with sensible coords."""
    state = await _run_one_turn(langgraph_server, "Fly me to Paris, France.")
    tools = _tool_names_from_state(state)
    assert "geocode_place" in tools, f"expected geocode_place in {tools}"

    fly_to_args: dict[str, Any] | None = None
    for message in state["values"]["messages"]:
        for call in (message.get("tool_calls") if isinstance(message, dict) else None) or []:
            if isinstance(call, dict) and call.get("name") == "fly_to":
                fly_to_args = call.get("args") or {}
                break
        if fly_to_args is not None:
            break

    if fly_to_args is not None:
        lon = float(fly_to_args.get("longitude"))
        lat = float(fly_to_args.get("latitude"))
        assert 1.5 < lon < 3.5, f"longitude {lon} not near Paris"
        assert 48.0 < lat < 49.5, f"latitude {lat} not near Paris"

    final = _final_assistant_text(state)
    assert final, "expected a final assistant message"


async def test_buffer_uses_viewport_from_map_state(langgraph_server: str) -> None:
    """When given map_state.viewport, the buffer tool should run with 500m."""
    paris_viewport = {
        "longitude": 2.349,
        "latitude": 48.864,
        "zoom": 12,
        "bounds": {"west": 2.2, "south": 48.8, "east": 2.5, "north": 48.93},
    }
    state = await _run_one_turn(
        langgraph_server,
        "Buffer the current view by 500 meters and add it as an overlay.",
        configurable={"map_state": {"viewport": paris_viewport}},
    )
    tools = _tool_names_from_state(state)
    # The model is allowed to call buffer_geometry (server-side) or
    # add_buffer_layer (UI stub) or both; require at least one.
    assert "buffer_geometry" in tools or "add_buffer_layer" in tools, (
        f"expected buffer_geometry or add_buffer_layer in {tools}"
    )

    # And the buffer distance the model picked has to be 500.
    found_distance: float | None = None
    for message in state["values"]["messages"]:
        for call in (message.get("tool_calls") if isinstance(message, dict) else None) or []:
            if not isinstance(call, dict):
                continue
            if call.get("name") in {"buffer_geometry", "add_buffer_layer"}:
                args = call.get("args") or {}
                found_distance = args.get("distance_m") or args.get("distance_meters")
                if found_distance is not None:
                    break
        if found_distance is not None:
            break
    assert found_distance == 500, f"expected distance 500, got {found_distance}"


async def test_features_within_uses_stub(langgraph_server: str) -> None:
    """The agent should call features_within and surface the stubbed names."""
    paris_viewport = {
        "longitude": 2.349,
        "latitude": 48.864,
        "zoom": 12,
        "bounds": {"west": 2.2, "south": 48.8, "east": 2.5, "north": 48.93},
    }
    state = await _run_one_turn(
        langgraph_server,
        "What features are in the current map view? List them by name.",
        configurable={"map_state": {"viewport": paris_viewport}},
    )
    tools = _tool_names_from_state(state)
    assert "features_within" in tools or "list_features_in_viewport" in tools, (
        f"expected features_within or list_features_in_viewport in {tools}"
    )

    final = _final_assistant_text(state).lower()
    # The stub returns "Eiffel Tower" and "Louvre Museum" — the model should
    # echo at least one of them back.
    assert "eiffel" in final or "louvre" in final, (
        f"expected Eiffel or Louvre in final message; got: {final!r}"
    )
