def test_classic_graph_imports_and_compiles() -> None:
    """Smoke test: the classic-LangChain graph imports and compiles."""
    from geogent_agent.classic_graph import graph

    assert graph is not None
    node_names = set(graph.get_graph().nodes)
    assert "classic_agent" in node_names


def test_agents_registry_lists_classic() -> None:
    from geogent_agent.agents import available_architectures, build_agent_graph

    assert "classic_langchain" in available_architectures()
    compiled = build_agent_graph("classic_langchain")
    assert "classic_agent" in set(compiled.get_graph().nodes)
