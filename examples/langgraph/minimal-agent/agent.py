"""Minimal LangGraph agent instrumented with Parlot configure()."""

from __future__ import annotations

import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from parlot.instrumentation.langgraph import close_session, configure

configure(agent_id="langgraph-minimal", version="0.1.0")


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


@tool
def lookup_time(city: str) -> str:
    """Return a fake local time for a city."""
    return f"The time in {city} is 15:00."


def _build_llm():
    if os.environ.get("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model="gpt-4o-mini").bind_tools([lookup_time])

    class _Echo:
        def invoke(self, messages, config=None):
            last = messages[-1]
            # After a tool result, return a final answer (avoid tool-call loops).
            if getattr(last, "type", None) == "tool" or last.__class__.__name__ == "ToolMessage":
                return AIMessage(content=str(getattr(last, "content", last)))
            text = getattr(last, "content", str(last))
            if "time" in str(text).lower():
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "lookup_time",
                            "args": {"city": "Paris"},
                            "id": "call_echo_1",
                            "type": "tool_call",
                        }
                    ],
                )
            return AIMessage(content=f"Echo: {text}")

    return _Echo()


def create_graph():
    llm = _build_llm()
    tools = ToolNode([lookup_time])

    def chatbot(state: State):
        return {"messages": [llm.invoke(state["messages"])]}

    def should_continue(state: State):
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    builder = StateGraph(State)
    builder.add_node("chatbot", chatbot)
    builder.add_node("tools", tools)
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges("chatbot", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "chatbot")
    return builder.compile()


def main() -> None:
    graph = create_graph()
    # Unique thread per process so re-runs do not collide with prior sessions.
    thread_id = f"demo-{os.getpid()}"
    thread = {"configurable": {"thread_id": thread_id}}

    result = graph.invoke(
        {"messages": [HumanMessage(content="What time is it in Paris?")]},
        config=thread,
    )
    for msg in result["messages"]:
        role = getattr(msg, "type", msg.__class__.__name__)
        print(f"{role}: {getattr(msg, 'content', msg)}")

    close_session(thread_id, reason="completed")
    print(f"done — thread_id={thread_id}; check Parlot for parlot.session / chat / execute_tool spans")


if __name__ == "__main__":
    main()
