from typing import TypedDict, Literal, Any, List, Dict
from datetime import datetime

# Narrowed Intent definitions to exactly the three we use
Intent = Literal["lookup", "analysis", "insights"]

class AgentState(TypedDict, total=False):
    user_query: str
    intent: Intent
    plan: Dict[str, Any]              # what to fetch/analyze
    raw_data: Dict[str, Any]          # unprocessed rows (JSON)
    analysis: Dict[str, Any]          # computed stats, deltas, anomalies
    insights: List[Any]               # tool/LLM-produced insights
    recs: List[Any]                   # tool/LLM-produced recommendations
    answer_md: str                    # final formatted markdown answer
    error: str
    start_time: datetime
