"""Classic LangChain agent (AgentExecutor + create_tool_calling_agent).

This is the "non-graph" architecture: a stock LangChain AgentExecutor that runs
its own tool-calling loop. It is backed by Amazon Bedrock by default so it can
be compared side-by-side with the LangGraph ReAct agent under `graphs/`.

To keep serving uniform with the rest of `apps/agent`, the AgentExecutor is
wrapped in a single-node LangGraph so `langgraph dev` can expose it alongside
the other architectures.
"""

from typing import Any

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import END, START, StateGraph

from geogent_agent.config import get_settings
from geogent_agent.models import get_chat_model
from geogent_agent.prompts import SYSTEM_PROMPT
from geogent_agent.state import GraphState
from geogent_agent.tools import TOOLS


def _build_agent_executor() -> AgentExecutor:
    settings = get_settings()
    # Force the Bedrock model for this architecture regardless of AGENT_MODEL.
    llm = get_chat_model(settings.bedrock_model_id)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )

    agent = create_tool_calling_agent(llm=llm, tools=TOOLS, prompt=prompt)
    return AgentExecutor(agent=agent, tools=TOOLS, verbose=False)


async def classic_agent_node(state: GraphState) -> dict:
    """Invoke the AgentExecutor with the latest human turn as `input`.

    Everything before the final human message becomes `chat_history`.
    """
    messages = state["messages"]

    last_human_idx = next(
        (i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)),
        None,
    )
    if last_human_idx is None:
        return {"messages": []}

    user_input = messages[last_human_idx].content
    chat_history = list(messages[:last_human_idx])

    executor = _build_agent_executor()
    result = await executor.ainvoke({"input": user_input, "chat_history": chat_history})

    return {"messages": [AIMessage(content=result["output"])]}


def build_classic_agent_graph() -> Any:
    """Wrap the classic LangChain AgentExecutor in a 1-node LangGraph.

    The executor runs the tool-calling loop internally, so the graph itself is
    trivial: START → classic_agent → END.
    """
    graph = StateGraph(GraphState)
    graph.add_node("classic_agent", classic_agent_node)
    graph.add_edge(START, "classic_agent")
    graph.add_edge("classic_agent", END)
    return graph.compile()
