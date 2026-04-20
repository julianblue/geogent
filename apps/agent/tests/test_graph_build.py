def test_graph_imports_and_compiles() -> None:
    """Smoke test: the compiled graph is importable and has expected nodes."""
    from geogent_agent.graph import graph

    assert graph is not None
    node_names = set(graph.get_graph().nodes)
    assert "agent" in node_names
    assert "tools" in node_names
