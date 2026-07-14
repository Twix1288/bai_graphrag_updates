import json
import asyncio
import time
from typing import List, Dict, Any

class EvaluationHarness:
    """
    Harness for testing the GraphRAG pipeline pre- and post-migration.
    """
    def __init__(self, golden_set_path: str):
        self.golden_set_path = golden_set_path
        self.golden_queries = self._load_queries()

    def _load_queries(self) -> List[Dict[str, Any]]:
        with open(self.golden_set_path, 'r') as f:
            return json.load(f)

    async def evaluate_query(self, engine, query: str) -> Dict[str, Any]:
        """
        Run a query against a specific GraphRAG query engine instance.
        """
        start_time = time.time()
        # In reality: result = await engine.search(query)
        # Mock result for now
        mock_retrieved_hotels = []
        latency = time.time() - start_time
        return {
            "retrieved_hotels": mock_retrieved_hotels,
            "latency": latency
        }

    def calculate_recall(self, expected: List[str], retrieved: List[str], k: int = 5) -> float:
        """Calculate Recall@k."""
        if not expected:
            return 1.0
        
        retrieved_k = retrieved[:k]
        hits = sum(1 for h in expected if h in retrieved_k)
        return hits / len(expected)

    async def run_shadow_mode_evaluation(self, old_engine, new_engine):
        """
        Runs the golden queries against both old and new query paths and diffs the results.
        """
        print(f"Running shadow mode evaluation on {len(self.golden_queries)} golden queries...")
        
        old_total_recall = 0.0
        new_total_recall = 0.0
        
        for idx, item in enumerate(self.golden_queries):
            query = item["query"]
            expected_hotels = item.get("expected_hotel_names", [])
            
            print(f"\n[{idx+1}/{len(self.golden_queries)}] Query: {query}")
            
            # Old Engine
            old_res = await self.evaluate_query(old_engine, query)
            old_recall = self.calculate_recall(expected_hotels, old_res["retrieved_hotels"])
            old_total_recall += old_recall
            
            # New Engine
            new_res = await self.evaluate_query(new_engine, query)
            new_recall = self.calculate_recall(expected_hotels, new_res["retrieved_hotels"])
            new_total_recall += new_recall
            
            print(f"Expected: {expected_hotels}")
            print(f"Old Engine -> Recall@5: {old_recall:.2f} | Latency: {old_res['latency']:.3f}s")
            print(f"New Engine -> Recall@5: {new_recall:.2f} | Latency: {new_res['latency']:.3f}s")
            
            if new_recall < old_recall:
                print("⚠️ REGRESSION DETECTED!")
            elif new_recall > old_recall:
                print("✅ IMPROVEMENT DETECTED!")
                
        old_avg = old_total_recall / len(self.golden_queries) if self.golden_queries else 0
        new_avg = new_total_recall / len(self.golden_queries) if self.golden_queries else 0
        
        print(f"\n=========================================")
        print(f"Old Engine Avg Recall@5: {old_avg:.2f}")
        print(f"New Engine Avg Recall@5: {new_avg:.2f}")
        print(f"Diff: {new_avg - old_avg:+.2f}")
        print(f"=========================================")

if __name__ == "__main__":
    harness = EvaluationHarness(golden_set_path="tests/golden_queries.json")
    # asyncio.run(harness.run_shadow_mode_evaluation(old_engine_mock, new_engine_mock))
    print("Harness ready. Need to instantiate engines and run shadow mode.")
