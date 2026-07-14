import time
import logging

logger = logging.getLogger(__name__)

class TokenBucketRateLimiter:
    """
    A real token-bucket rate limiter for the NL2Cypher sandbox.
    Uses Redis (mocked here for scaffolding) to track tokens per user/session.
    """
    def __init__(self, capacity: int, refill_rate_per_sec: float, redis_client=None):
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
        self.redis = redis_client
        # Mock local store for scaffolding (should be in Redis for production distributed locking)
        self._local_store = {}

    async def consume(self, client_id: str, tokens: int = 1) -> bool:
        """
        Consumes tokens from the bucket. Returns True if successful, False if rate limited.
        """
        now = time.time()
        
        if self.redis:
            # In production, use a Redis Lua script to ensure atomic check-and-set
            pass
            
        # Local mock logic to demonstrate the algorithm
        if client_id not in self._local_store:
            self._local_store[client_id] = {"tokens": self.capacity, "last_refill": now}
            
        bucket = self._local_store[client_id]
        
        # Refill
        elapsed = now - bucket["last_refill"]
        new_tokens = int(elapsed * self.refill_rate)
        if new_tokens > 0:
            bucket["tokens"] = min(self.capacity, bucket["tokens"] + new_tokens)
            bucket["last_refill"] = now
            
        if bucket["tokens"] >= tokens:
            bucket["tokens"] -= tokens
            return True
        else:
            logger.warning(f"Rate limit exceeded for client {client_id}")
            return False
