"""
Sub-Location planning chat (final_check.md §9 ChatPlanning).

Flow: pick a destination, describe your trip in plain English, get its
sub-locations ranked by fit — each with a price tier, a "why this fits you"
line, and one honest tradeoff. The ranking is the deterministic engine in
src/ranking.py; the LLM only maps your words to weights and writes the copy.
"""
import asyncio
import logging

from src.clients import get_neo4j_client, get_llm_client, get_embedding_client
from src.engine import GraphRAGQueryEngine
from src.presentation import render_sublocations

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("src.clients").setLevel(logging.WARNING)
logging.getLogger("neo4j").setLevel(logging.WARNING)
logging.getLogger("src.sublocation_intel").setLevel(logging.WARNING)


async def _list_destinations(neo4j):
    res = await neo4j.execute_query(
        "MATCH (d:Destination)<-[:PART_OF]-(:Region)<-[:PART_OF]-(s:SubLocation) "
        "RETURN d.name AS name, count(s) AS subs ORDER BY subs DESC"
    )
    return [(r.data()["name"], r.data()["subs"]) for r in res.records]


def _print_cards(result):
    print("\n" + render_sublocations(result) + "\n")


async def main():
    neo4j = get_neo4j_client()
    engine = GraphRAGQueryEngine(neo4j, get_embedding_client(), get_llm_client())

    print("\n==============================================")
    print("   Sub-Location Planner")
    print("==============================================")
    dests = await _list_destinations(neo4j)
    if dests:
        print("Destinations with sub-locations:")
        for name, subs in dests:
            print(f"  - {name} ({subs} sub-locations)")
    print("\nType 'quit' to exit.\n")

    try:
        while True:
            dest = input("Destination: ").strip()
            if dest.lower() in ("quit", "exit"):
                break
            if not dest:
                continue
            prefs = input("What are you looking for? ").strip()
            if prefs.lower() in ("quit", "exit"):
                break
            print("\nRanking...")
            try:
                result = await engine._execute_find_sublocations_for_destination(dest, prefs)
                _print_cards(result)
            except Exception as e:  # noqa: BLE001
                print(f"  Error: {e}")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        print("\nGoodbye!")
        await neo4j.close()


if __name__ == "__main__":
    asyncio.run(main())
