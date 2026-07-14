import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==========================================
# Neo4j Client setup
# ==========================================
from neo4j import GraphDatabase, AsyncGraphDatabase

def get_neo4j_client():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    
    # We use the async driver for async operations
    driver = AsyncGraphDatabase.driver(uri, auth=(username, password))
    return driver

# ==========================================
# Redis Client setup (for distributed locks)
# ==========================================
import redis.asyncio as redis

def get_redis_client():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    return redis.from_url(redis_url)

# ==========================================
# LLM / Embeddings Client setup
# ==========================================
import openai

def get_openai_client():
    api_key = os.getenv("NVIDIA_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("NVIDIA_LLM_API_KEY (or OPENAI_API_KEY) must be provided in .env")
    return openai.AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

# A simple wrapper for our use cases to mimic the old interface
class OpenAIWrapper:
    def __init__(self, client):
        self.client = client
    
    async def complete(self, prompt=None, messages=None, **kwargs):
        if messages is None:
            messages = [{"role": "user", "content": prompt}]
            
        response = await self.client.chat.completions.create(
            model="nvidia/nemotron-mini-4b-instruct",
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content

class NvidiaEmbeddingWrapper:
    """
    Wrapper for NVIDIA NIM embeddings API (e.g. nv-embedcode-7b-v1)
    For this example, we mock the call, but this is where the real HTTP 
    request to the NIM endpoint would go.
    """
    def __init__(self):
        self.api_key = os.getenv("NVIDIA_EMBEDDING_API_KEY") or os.getenv("NVIDIA_API_KEY")
        if not self.api_key:
            raise ValueError("NVIDIA_EMBEDDING_API_KEY (or NVIDIA_API_KEY) must be provided in .env")
            
    async def embed(self, text: str, input_type: str = "query"):
        """
        Embed text via NVIDIA NIM.

        `input_type` must be "passage" for text being stored/indexed and "query"
        for search-time retrieval — e5 asymmetric models encode the two differently,
        and using "query" for stored content measurably hurts recall.
        """
        import ssl
        import certifi
        import aiohttp
        # TLS verification stays ON, but pinned to the certifi CA bundle so it works
        # on hosts whose system trust store is incomplete (common on macOS Python).
        # This is the secure alternative to the old verify_ssl=False, which exposed
        # the API key to MITM.
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                "https://integrate.api.nvidia.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"input": [text], "input_type": input_type, "model": "nvidia/nv-embedqa-e5-v5"}
            ) as resp:
                data = await resp.json()
                if "data" not in data:
                    raise RuntimeError(f"NVIDIA API Error: {data}")
                return data["data"][0]["embedding"]

def get_llm_client():
    return OpenAIWrapper(get_openai_client())

def get_embedding_client():
    return NvidiaEmbeddingWrapper()
