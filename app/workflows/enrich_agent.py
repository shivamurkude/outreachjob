"""Enrich flow: wrap enrichment service in a graph."""

from typing import TypedDict

from beanie import PydanticObjectId
from langgraph.graph import END, START, StateGraph


class EnrichState(TypedDict):
    user_id: str
    recipient_item_ids: list[str]
    results: list[dict]
    error: str


async def _run_enrich(state: EnrichState) -> dict:
    from app.services import enrichment as enrichment_service

    user_id = state["user_id"]
    ids = state["recipient_item_ids"]
    try:
        oids = [PydanticObjectId(x) for x in ids]
        results_list = await enrichment_service.enrich_bulk(PydanticObjectId(user_id), oids)
        results = [
            {"recipient_item_id": str(r.recipient_item.ref), "chosen_email": r.chosen_email, "role": r.role}
            for r in results_list
        ]
        return {"results": results, "error": ""}
    except Exception as e:
        return {"results": [], "error": str(e)}


def build_enrich_graph():
    builder = StateGraph(EnrichState)
    builder.add_node("enrich", _run_enrich)
    builder.add_edge(START, "enrich")
    builder.add_edge("enrich", END)
    return builder.compile()


async def run_enrich_agent(user_id: str, recipient_item_ids: list[str]) -> dict:
    """Run enrich agent; returns state with results or error."""
    graph = build_enrich_graph()
    initial: EnrichState = {"user_id": user_id, "recipient_item_ids": recipient_item_ids, "results": [], "error": ""}
    result = await graph.ainvoke(initial)
    return dict(result)
