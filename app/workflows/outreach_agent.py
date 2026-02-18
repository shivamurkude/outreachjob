"""Outreach flow: recipient selection, suppression, schedule plan, credit estimate for a campaign."""

from typing import Any, TypedDict

from beanie import PydanticObjectId
from langgraph.graph import END, START, StateGraph


class OutreachState(TypedDict):
    campaign_id: str
    user_id: str
    recipient_ids: list[str]
    schedule_plan: list[dict[str, Any]]
    credits_required: int
    credits_per_send: int
    error: str


async def _plan_outreach(state: OutreachState) -> dict:
    from datetime import datetime, timedelta
    from app.core.config import get_settings
    from app.models.campaign import Campaign
    from app.models.recipient_item import RecipientItem
    from app.models.recipient_list import RecipientList
    from app.services.suppression import list_suppressed_emails

    campaign_id = state["campaign_id"]
    user_id = state["user_id"]
    try:
        campaign = await Campaign.get(PydanticObjectId(campaign_id))
        if not campaign or str(campaign.user.ref) != user_id:
            return {"error": "Campaign not found"}
        if not campaign.recipient_list_id:
            return {"recipient_ids": [], "schedule_plan": [], "credits_required": 0, "credits_per_send": get_settings().credits_per_send}
        rlist = await RecipientList.get(PydanticObjectId(campaign.recipient_list_id))
        if not rlist:
            return {"error": "List not found"}
        items = await RecipientItem.find(RecipientItem.list.id == rlist.id).limit(500).to_list()
        suppressed = await list_suppressed_emails(user_id)
        items = [i for i in items if i.email not in suppressed and ((i.chosen_email or i.email) not in suppressed)]
        credits_per_send = get_settings().credits_per_send
        credits_required = len(items) * credits_per_send
        send_at = datetime.utcnow() + timedelta(minutes=1)
        schedule_plan = []
        for item in items:
            schedule_plan.append({
                "recipient_id": str(item.id),
                "email": item.chosen_email or item.email,
                "send_at": send_at.isoformat(),
            })
            send_at = send_at + timedelta(seconds=30)
        return {
            "recipient_ids": [str(i.id) for i in items],
            "schedule_plan": schedule_plan,
            "credits_required": credits_required,
            "credits_per_send": credits_per_send,
            "error": "",
        }
    except Exception as e:
        return {"error": str(e)}


def build_outreach_graph():
    builder = StateGraph(OutreachState)
    builder.add_node("plan", _plan_outreach)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", END)
    return builder.compile()


async def run_outreach(campaign_id: str, user_id: str) -> dict:
    """Run outreach agent; return schedule plan and credit estimate."""
    graph = build_outreach_graph()
    initial: OutreachState = {
        "campaign_id": campaign_id,
        "user_id": user_id,
        "recipient_ids": [],
        "schedule_plan": [],
        "credits_required": 0,
        "credits_per_send": 0,
        "error": "",
    }
    result = await graph.ainvoke(initial)
    return dict(result)
