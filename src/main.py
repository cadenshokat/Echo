# src/main.py

import os
import sys
from dotenv import load_dotenv
from datetime import datetime
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes import (
    router_node,
    planner_node,
    fetch_data_node,
    analyze_node,
    insights_llm_node,
    recs_llm_node,
    compose_answer_node,
    clarification_node,
    error_node
)
from agent.conditions import needs_more_info, failed_verification

def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # Register all of your node functions
    g.add_node("router",       router_node)
    g.add_node("planner",      planner_node)
    g.add_node("fetch_data",   fetch_data_node)
    g.add_node("analyze",      analyze_node)
    g.add_node("insights",     insights_llm_node)
    g.add_node("recs",         recs_llm_node)
    g.add_node("compose",      compose_answer_node)
    g.add_node("clarify",      clarification_node)
    g.add_node("error",        error_node)

    # Entry point
    g.set_entry_point("router")

    # Always go router → planner
    g.add_edge("router", "planner")

    # After planner: insights-only, clarify if needed, else fetch
    def after_planner(s: AgentState):
        if s["intent"] == "insights":
            return "insights"
        if needs_more_info(s):
            return "clarify"
        return "fetch_data"

    g.add_conditional_edges(
        "planner",
        after_planner,
        {"insights": "insights", "clarify": "clarify", "fetch_data": "fetch_data"}
    )

    # After fetch_data: error? quick‑lookup? or analyze
    def after_fetch(s: AgentState):
        if "error" in s:
            return "error"
        if s["intent"] == "lookup":
            return "compose"
        return "analyze"

    g.add_conditional_edges(
        "fetch_data",
        after_fetch,
        {"error": "error", "compose": "compose", "analyze": "analyze"}
    )

    # analysis → insights → recs → compose → verify → end
    g.add_edge("analyze",   "insights")
    g.add_edge("insights",  "recs")
    g.add_edge("recs",      "compose")
    g.add_edge("compose",   "verify")

    # If verification fails, re‑compose; else terminate

    # clarify and error terminate
    g.add_edge("clarify", END)
    g.add_edge("error",   END)

    return g

def main():
    # load .env if present
    load_dotenv()

    # require creds
    if not os.getenv("openai_api_key"):
        print("❌ Missing OPENAI_API_KEY"); sys.exit(1)
    if not os.getenv("supabase_url") or not os.getenv("supabase_key"):
        print("❌ Missing SUPABASE_URL/SUPABASE_KEY"); sys.exit(1)

    # read user query
    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
    else:
        user_query = input("🗣  Your query: ").strip()

    # seed initial state
    init_state: AgentState = {
        "user_query": user_query,
        "start_time": datetime.now()
    }

    # build & run the graph
    graph = build_graph()
    final_state = graph.run(init_state)

    # output markdown answer
    print("\n" + final_state.get("answer_md", "No answer generated.") + "\n")

if __name__ == "__main__":
    main()
