from datetime import date, timedelta
from agent.state import AgentState
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage
from agent.tools import (
    get_campaign_metrics,
    get_ad_metrics,
    get_publisher_metrics,
    detect_anomalies,
    generate_insights,
    recommend_actions,
)
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("openai_api_key")

llm = ChatOpenAI(
    model="gpt-4.1",
    temperature=3.5,
    max_tokens=1_000_000,
    timeout=None,
    max_retries=2,
)

def router_node(state: AgentState) -> AgentState:
    user_query = state.get("user_query", "")

    messages = [
        SystemMessage(content=(
                "You are a router. Classify the user query into one of exactly: `lookup`, `analysis`, or `insights`."
                "Respond with **only** the label."
            )),
        HumanMessage(content=user_query)
    ]

    reply = llm.invoke(messages)
    state["intent"] = reply.content.strip()
    return state

def planner_node(state: AgentState) -> AgentState:
    """Build a plan dict based on intent."""
    intent = state["intent"]
    plan: dict = {"intent": intent}

    # Quick lookups get parsed later in fetch_data
    if intent == "lookup":
        plan["query"] = state["user_query"]

    # Full audit: fetch everything for last 7 days
    elif intent == "analysis":
        today = date.today()
        plan.update({
            "campaign_ids": None,           # None→all active campaigns
            "date_from": (today - timedelta(days=7)).isoformat(),
            "date_to":   today.isoformat(),
            "anomaly_threshold": 2.0,
            "top_n_publishers": 20,
            # flags to drive fetch_data
            "need_campaign_ts": True,
            "need_ad_ts":       True,
            "need_pub_ts":      True,
        })

    # Insights only: assume analysis already in state
    elif intent == "insights":
        # user must have a prior analysis_report in state["analysis"]
        plan["analysis_report"] = state.get("analysis", {})

    state["plan"] = plan
    return state

def fetch_data_node(state: AgentState) -> AgentState:
    """Fetch raw JSON from your Supabase DAL based on the plan."""
    plan = state["plan"]
    data: dict = {}

    try:
        if plan["intent"] == "lookup":
            # let your get_* functions parse the free‐form query
            data = get_campaign_metrics(plan["query"]) or {}
            data.update(get_ad_metrics(plan["query"]) or {})

        elif plan["intent"] == "analysis":
            # 1) Campaign time-series
            if plan.get("need_campaign_ts"):
                data["campaign_metrics"] = get_campaign_metrics(
                    campaign_ids=plan["campaign_ids"],
                    date_from=plan["date_from"],
                    date_to=plan["date_to"],
                )
            # 2) Ad time-series
            if plan.get("need_ad_ts"):
                data["ad_metrics"] = get_ad_metrics(
                    campaign_ids=plan["campaign_ids"],
                    date_from=plan["date_from"],
                    date_to=plan["date_to"],
                )
            # 3) Publisher snapshot
            if plan.get("need_pub_ts"):
                data["publisher_metrics"] = get_publisher_metrics(
                    campaign_id=plan["campaign_ids"],
                    top_n=plan["top_n_publishers"],
                )

        elif plan["intent"] == "insights":
            # nothing to fetch – use existing analysis_report
            data["analysis_report"] = plan["analysis_report"]

        state["raw_data"] = data

    except Exception as e:
        state["error"] = str(e)

    return state

def analyze_node(state: AgentState) -> AgentState:
    """Compute anomalies / deltas on raw_data."""
    if "error" in state:
        return state

    plan = state["plan"]
    rd = state["raw_data"]
    analysis: dict = {}

    if plan["intent"] == "lookup":
        # raw_data already contains the numeric values
        analysis = rd

    elif plan["intent"] == "analysis":
        thresh = plan["anomaly_threshold"]
        # flag campaign-level
        cms = rd.get("campaign_metrics", [])
        analysis["campaign_anomalies"] = detect_anomalies(cms, threshold=thresh)
        # flag ad-level
        ads = rd.get("ad_metrics", [])
        analysis["ad_anomalies"] = detect_anomalies(ads, threshold=thresh)
        # flag publisher-level
        pubs = rd.get("publisher_metrics", [])
        analysis["publisher_anomalies"] = detect_anomalies(pubs, threshold=thresh)

    elif plan["intent"] == "insights":
        # pass through the existing report
        analysis = rd.get("analysis_report", {})

    state["analysis"] = analysis
    return state

def insights_llm_node(state: AgentState) -> AgentState:
    if state["intent"] in ("analysis" "insights"):
        analysis = state["analysis"]
        prompt = SystemMessage(content=(
            "You are a Taboola Channel Manager for hear.com."
            "Here is a report of anomalies found:"
            f"{analysis!r}\n\n"
            "Generate a complete holistic analysis filled with insights on this data."
        ))
        resp = llm([prompt])

        state["insights"] = resp.content
    return state

def recs_llm_node(state: AgentState) -> AgentState:
    """Generate prioritized recommendations."""
    if state["intent"] in ("analysis", "insights"):
        analysis = state["analsis"]
        prompt = SystemMessage(content=(
            "You are a Taboola Channel Manager for hear.com."
            "Based on the anomalies report below, suggest important, fact based recommendations and next steps."
            "(e.g. `Pause campaign X`, `Increase spend on ads X, Y, and Z`, etc).\n\n"
            f"{analysis!r}"
        ))
        resp = llm([prompt])
        state["recs"] = resp.content

def compose_answer_node(state: AgentState) -> AgentState:
    """Build a markdown answer for the user."""
    if "error" in state:
        state["answer_md"] = f"⚠️ Error: {state['error']}"
        return state

    intent = state["intent"]
    md = []

    if intent == "lookup":
        md.append("## Quick Metrics Lookup\n")
        for key, val in state["raw_data"].items():
            md.append(f"**{key}**:\n```\n{val}\n```")

    elif intent == "analysis":
        md.append("## Full Campaign Audit\n")
        # anomalies
        for level in ("campaign", "ad", "publisher"):
            anoms = state["analysis"].get(f"{level}_anomalies", [])
            md.append(f"### {level.title()} Anomalies\n")
            md.append("\n".join(f"- {a}" for a in anoms) or "No anomalies detected.\n")

        # recommendations
        md.append("## Recommendations\n")
        md.append("\n".join(f"- {r}" for r in state.get("recs", [])) or "No recommendations.")

    elif intent == "insights":
        md.append("## Strategic Insights\n")
        md.append("\n".join(f"- {i}" for i in state.get("insights", [])) or "No insights generated.")

    state["answer_md"] = "\n\n".join(md)
    return state

def clarification_node(state: AgentState) -> AgentState:
    """If planner needs more info (e.g. missing dates), ask user."""
    # Simplest example: if dates are None in analysis
    if state["intent"] == "analysis" and (not state["plan"].get("date_from")):
        state["answer_md"] = (
            "Could you please specify the date range for your audit?\n"
            "(e.g. `2025-07-10 to 2025-07-17`)"
        )
    return state

def error_node(state: AgentState) -> AgentState:
    """Graceful fallback if anything explodes."""
    state.setdefault("answer_md", "")
    state["answer_md"] += "\n\nAn unexpected error occurred; please try again."
    return state
