"""Verify flow: wrap verification service in a graph (single or bulk)."""

from typing import TypedDict

from beanie import PydanticObjectId
from langgraph.graph import END, START, StateGraph


class VerifyState(TypedDict):
    user_id: str
    emails: list[str]
    results: list[dict]
    error: str


async def _run_verify(state: VerifyState) -> dict:
    from app.services import verification as verification_service

    user_id = state["user_id"]
    emails = state["emails"]
    try:
        if len(emails) == 1:
            evr = await verification_service.verify_email_for_user(PydanticObjectId(user_id), emails[0])
            results = [{"email": evr.email, "result": evr.result, "syntax_valid": evr.syntax_valid, "mx_valid": evr.mx_valid}]
        else:
            results_list = await verification_service.verify_bulk(PydanticObjectId(user_id), emails)
            results = [{"email": r.email, "result": r.result, "syntax_valid": r.syntax_valid, "mx_valid": r.mx_valid} for r in results_list]
        return {"results": results, "error": ""}
    except Exception as e:
        return {"results": [], "error": str(e)}


def build_verify_graph():
    builder = StateGraph(VerifyState)
    builder.add_node("verify", _run_verify)
    builder.add_edge(START, "verify")
    builder.add_edge("verify", END)
    return builder.compile()


async def run_verify_agent(user_id: str, emails: list[str]) -> dict:
    """Run verify agent; returns state with results or error."""
    graph = build_verify_graph()
    initial: VerifyState = {"user_id": user_id, "emails": emails, "results": [], "error": ""}
    result = await graph.ainvoke(initial)
    return dict(result)
