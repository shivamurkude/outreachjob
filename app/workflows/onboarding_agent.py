"""Onboarding flow: determine next step for user (Gmail, list, template, campaign)."""

from typing import TypedDict

from beanie import PydanticObjectId
from langgraph.graph import END, START, StateGraph


class OnboardingState(TypedDict):
    user_id: str
    has_gmail: bool
    has_list: bool
    has_template: bool
    next_step: str
    completed: bool


async def _check_onboarding(state: OnboardingState) -> dict:
    from app.models.gmail_account import GmailAccount
    from app.models.recipient_list import RecipientList
    from app.models.template import Template

    user_id = state["user_id"]
    uid = PydanticObjectId(user_id)
    has_gmail = await GmailAccount.find_one(GmailAccount.user.id == uid, GmailAccount.revoked == False) is not None  # noqa: E712
    has_list = await RecipientList.find_one(RecipientList.user.id == uid) is not None
    has_template = await Template.find_one(Template.user.id == uid) is not None

    if not has_gmail:
        next_step = "connect_gmail"
    elif not has_list:
        next_step = "upload_list"
    elif not has_template:
        next_step = "create_template"
    else:
        next_step = "create_campaign"
    completed = has_gmail and has_list and has_template
    return {
        "has_gmail": has_gmail,
        "has_list": has_list,
        "has_template": has_template,
        "next_step": next_step,
        "completed": completed,
    }


def build_onboarding_graph():
    builder = StateGraph(OnboardingState)
    builder.add_node("check", _check_onboarding)
    builder.add_edge(START, "check")
    builder.add_edge("check", END)
    return builder.compile()


async def run_onboarding(user_id: str) -> dict:
    """Run onboarding agent; return state with next_step and flags."""
    graph = build_onboarding_graph()
    initial: OnboardingState = {
        "user_id": user_id,
        "has_gmail": False,
        "has_list": False,
        "has_template": False,
        "next_step": "",
        "completed": False,
    }
    result = await graph.ainvoke(initial)
    return dict(result)
