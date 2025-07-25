# src/agent/tools.py

import os
from typing import List, Dict, Any, Optional
from supabase import create_client, Client

# ─── Supabase client setup ─────────────────────────────────────────────────────

SUPABASE_URL = "https://srdciudllftvhhjzxknu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNyZGNpdWRsbGZ0dmhoanp4a251Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MjcyMDYzNSwiZXhwIjoyMDY4Mjk2NjM1fQ.EbBjGvisDeg2LLATqQBH7NFB1NGaRU9adjboYfX4M9E"
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Please set SUPABASE_URL and SUPABASE_KEY env vars")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ─── Data-Access Tools ──────────────────────────────────────────────────────────

def get_campaign_metrics(
    campaign_ids: Optional[List[str]] = None,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch daily campaign metrics (DoD + 7d window) from campaign_metrics_daily.
    """
    q = supabase.table("campaign_metrics_daily").select(
        "campaign_id, date, clicks, impressions, spent, ctr, vctr, cpc, cpa, cpa_actions_num, cpa_conversion_rate, conversions_value"
    )
    if campaign_ids:
        q = q.in_("campaign_id", campaign_ids)
    if date_from:
        q = q.gte("date", date_from)
    if date_to:
        q = q.lte("date", date_to)

    resp = q.execute()
    return getattr(resp, "data", resp.get("data", []))


def get_ad_metrics(
    campaign_ids: Optional[List[str]] = None,
    date_from:    Optional[str] = None,
    date_to:      Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch daily ad metrics (DoD + 7d window) from ad_metrics_daily.
    """
    q = supabase.table("ad_metrics_daily").select(
        "ad_id, campaign_id, created_at, impressions, clicks, spent, actions_num, conversions_value, cpm, ctr, cpc, cpa, cpa_conversion_rate"
    )
    if campaign_ids:
        q = q.in_("campaign_id", campaign_ids)
    if date_from:
        q = q.gte("created_at", date_from)
    if date_to:
        q = q.lte("created_at", date_to)

    resp = q.execute()
    return getattr(resp, "data", resp.get("data", []))


def get_publisher_metrics(
    campaign_id: str,
    top_n:       int = 20
) -> List[Dict[str, Any]]:
    """
    Fetch the top-N publishers by spend for a given campaign
    from active_campaign_sites.
    """
    resp = (
        supabase
        .table("active_campaign_sites")
        .select(
            "site_id, site, site_name, clicks, impressions, spend, conversions_value, ctr, cpm, cpc, cpa_actions_num"
        )
        .eq("campaign_id", campaign_id)
        .order("spend", desc=True)
        .limit(top_n)
        .execute()
    )
    return getattr(resp, "data", resp.get("data", []))


# ─── Analytics Tools ────────────────────────────────────────────────────────────

def detect_anomalies(
    data:      List[Dict[str, Any]],
    threshold: float = 2.0
) -> List[str]:
    """
    Simple z-score anomaly detection on the 'spent' field.
    Returns a list of human-readable strings for any rows where |z| >= threshold.
    """
    # collect spent values
    vals = [float(r["spent"]) for r in data if r.get("spent") is not None]
    if not vals:
        return []

    mean = sum(vals) / len(vals)
    var  = sum((v - mean) ** 2 for v in vals) / len(vals)
    std  = var**0.5 if var > 0 else 0

    anomalies: List[str] = []
    for row in data:
        spent = row.get("spent")
        if spent is None or std == 0:
            continue
        z = (spent - mean) / std
        if abs(z) >= threshold:
            # identify by campaign_id or ad_id, plus date
            ident = row.get("campaign_id") or row.get("ad_id", "<unknown>")
            date  = row.get("date") or row.get("created_at", "")
            anomalies.append(
                f"{ident} on {date}: spent={spent:.2f} (z={z:.2f})"
            )
    return anomalies


# ─── Insight & Recommendation Tools ────────────────────────────────────────────

def generate_insights(analysis_report: Dict[str, Any]) -> List[str]:
    """
    Summarize how many anomalies were found at each level.
    """
    insights: List[str] = []
    for level in ("campaign", "ad", "publisher"):
        key = f"{level}_anomalies"
        items = analysis_report.get(key, [])
        if items:
            insights.append(f"🔍 Found {len(items)} anomalies at the **{level}** level.")
        else:
            insights.append(f"✅ No anomalies detected at the **{level}** level.")
    return insights


def recommend_actions(analysis_report: Dict[str, Any]) -> List[str]:
    """
    Based on what was flagged, emit simple pause/increase/hold suggestions.
    """
    recs: List[str] = []
    if analysis_report.get("campaign_anomalies"):
        recs.append("• Consider pausing or re-budgeting underperforming campaigns.")
    if analysis_report.get("ad_anomalies"):
        recs.append("• Optimize or swap out low-CTR ads.")
    if analysis_report.get("publisher_anomalies"):
        recs.append("• Review top publishers for outlier spend or performance dips.")
    if not recs:
        recs.append("• No immediate actions needed. Continue to monitor performance.")
    return recs
