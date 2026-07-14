import asyncio
import pytest
from src.rate_limiter import TokenBucketRateLimiter

@pytest.mark.asyncio
async def test_rate_limiter_rapid_consumption():
    # Capacity 2, so it should allow 2 immediate calls, then block the 3rd
    limiter = TokenBucketRateLimiter(capacity=2, refill_rate_per_sec=0.1)
    
    # 1. First call should succeed
    allowed1 = await limiter.consume("user_123")
    assert allowed1 is True, "First call should be allowed"
    
    # 2. Second call should succeed
    allowed2 = await limiter.consume("user_123")
    assert allowed2 is True, "Second call should be allowed"
    
    # 3. Third call should fail (bucket empty)
    allowed3 = await limiter.consume("user_123")
    assert allowed3 is False, "Third call should be blocked (rate limited)"
    
    # 4. Wait for 10 seconds (1 token at 0.1/sec)
    # Using a sleep or manual time mock. For a real unit test we'd patch time.time.
    # Here we just manually adjust the local store to simulate time passing.
    limiter._local_store["user_123"]["last_refill"] -= 11.0
    
    # 5. Fourth call should now succeed
    allowed4 = await limiter.consume("user_123")
    assert allowed4 is True, "Fourth call should succeed after refill"
    print("Rate limiter tests passed successfully.")

if __name__ == "__main__":
    asyncio.run(test_rate_limiter_rapid_consumption())
