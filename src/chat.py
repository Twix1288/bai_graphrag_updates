import asyncio
import sys
import logging
from src.clients import get_neo4j_client, get_llm_client, get_embedding_client
from src.engine import GraphRAGQueryEngine

# Silence noisy loggers for the chat interface
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("src.clients").setLevel(logging.WARNING)
logging.getLogger("neo4j").setLevel(logging.WARNING)

async def main():
    print("Initializing GraphRAG Engine...")
    neo4j_client = get_neo4j_client()
    llm_client = get_llm_client()
    embedding_client = get_embedding_client()
    
    engine = GraphRAGQueryEngine(neo4j_client, embedding_client, llm_client)
    
    print("\n==============================================")
    print("   GraphRAG Chat Interface is Online! ")
    print("   Type 'exit' or 'quit' to stop.")
    print("==============================================\n")
    
    history = []
    
    while True:
        try:
            query = input("You: ")
            if query.strip().lower() in ['exit', 'quit']:
                break
                
            print("GraphRAG: Thinking...")
            result = await engine.search(query, history=history)
            
            response = result.get("results", result)
            if isinstance(response, dict) and "error" in response:
                print(f"Error: {response['error']}")
                response_str = str(response)
            else:
                print(f"\n[GraphRAG Answer]\n{response}\n")
                response_str = str(response)
                
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": response_str})
            
        except EOFError:
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nError: {e}")
            
    print("Goodbye!")

if __name__ == "__main__":
    asyncio.run(main())
