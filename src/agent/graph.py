# src/agent/graph.py
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes import router_node, planner_node, fetch_data_node, analyze_node, insights_llm_node, recs_llm_node, compose_answer_node, clarification_node, error_node
from graphviz import graphs
from agent.conditions import needs_more_info, failed_verification

graph = StateGraph(AgentState)

graph.add_node("router", router_node)
graph.add_node("planner", planner_node)
graph.add_node("fetch_data", fetch_data_node)
graph.add_node("analyze", analyze_node)
graph.add_node("insights_llm", insights_llm_node)
graph.add_node("recs_llm", recs_llm_node)
graph.add_node("compose", compose_answer_node)
graph.add_node("clarify", clarification_node)
graph.add_node("error", error_node)

# Entry
graph.set_entry_point("router")

# Happy path edges
graph.add_edge("router", "planner")
graph.add_edge("planner", "fetch_data")
graph.add_edge("fetch_data", "analyze")
graph.add_edge("analyze", "insights_llm")
graph.add_edge("insights_llm", "recs_llm")
graph.add_edge("recs_llm", "compose")
graph.add_edge("compose", END)

# Conditional branches (pseudo conditions; implement in node funcs)
graph.add_conditional_edges(
    "planner",
    lambda s: "clarify" if needs_more_info(s) else "fetch_data",
    {
        "clarify": "clarify",
        "fetch_data": "fetch_data"
    }
)

graph.add_conditional_edges(
    "fetch_data",
    lambda s: "error" if "error" in s else "analyze",
    {
        "error": "error",
        "analyze": "analyze"
    }
)

app = graph.compile()

graph = app.get_graph()
png = graph.draw_mermaid_png()

with open("my_graph.png", "wb") as f:
    f.write(png)