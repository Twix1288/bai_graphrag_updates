import asyncio
import json
from src.engine import GraphRAGQueryEngine
from src.clients import get_neo4j_client, get_llm_client, get_embedding_client
from src.presentation import render_sublocations

async def main():
    print("Initializing GraphRAG Engine...")
    neo4j = get_neo4j_client()
    llm = get_llm_client()
    embeddings = get_embedding_client()
    
    engine = GraphRAGQueryEngine(neo4j, embeddings, llm)
    print("\n✅ Ready! Type 'quit' or 'exit' to stop.")
    print("-" * 50)
    
    history = []
    while True:
        try:
            query = input("\n[YOU]: ")
            if query.lower() in ['quit', 'exit']:
                break
            
            if not query.strip():
                continue
                
            history.append({"role": "user", "content": query})
                
            print("[GraphRAG]: Thinking...")
            results = await engine.search(query, history=history)

            # Ranked sub-location results get a friendly, scored card layout.
            if isinstance(results, dict) and results.get("tool_used") == "sublocation_resolver":
                rendered = render_sublocations(results)
                print("\n[GraphRAG]:\n" + rendered)
                history.append({"role": "assistant", "content": rendered})
            elif isinstance(results, dict) and "results" in results:
                print("\n[GraphRAG]:", results["results"])
                history.append({"role": "assistant", "content": str(results["results"])})
                if "tool_used" in results:
                    print(f"\n*(Internal tool used: {results['tool_used']})*")
            else:
                print("\n[GraphRAG]:", json.dumps(results, indent=2))

            # Keep only last 10 messages (5 turns)
            if len(history) > 10:
                history = history[-10:]
                
        except (KeyboardInterrupt, EOFError):
            break
        except Exception as e:
            print(f"\n[GraphRAG Error]: {e}")
            
    print("\nClosing connections...")
    await neo4j.close()

if __name__ == "__main__":
    asyncio.run(main())
