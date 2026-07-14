# GraphRAG Production-Readiness Implementation Plan

## Goal Description
Transform the GraphRAG codebase from a demo-ready scaffold into a production-ready system by addressing three critical HIGH blockers (Cypher injection, broken routing logic, ignored query timeouts) and three MEDIUM gaps (lack of test coverage, disabled TLS verification, incorrect embedding input types).

## User Review Required
> [!IMPORTANT]
> **SubLocation vs. Vibe Summary Routing Decision**
> To fix the routing conflict where destinations now resolve successfully (thus skipping the sub-location ranker), I propose checking the resolved entity type directly in Neo4j. If the resolved entity has incoming `[:PART_OF]` relationships from `SubLocation` nodes, we route to `_execute_find_sublocations_for_destination`. Otherwise, we route to `_execute_destination_vibe_summary`.
> 
> *Is this dynamic routing acceptable, or would you prefer relying on an explicit LLM classification in `_extract_entities_from_query` (e.g., adding an `intent` field to the JSON schema) to distinguish between general vibes and specific sublocation discovery?*

## Proposed Changes

---

### Core Engine & Routing (`engine.py`)

#### [MODIFY] [engine.py](file:///Users/rishitagnihotri/bai_internship/GraphRag/src/engine.py)
1. **Fix Cypher Injection**: 
   - Modify `_nl2cypher_fallback` to parameterize the raw user query.
   - *Change*: `cypher = "MATCH (n) WHERE n.name = $query RETURN n LIMIT 1"` and pass `{"query": natural_query}` to the executor. (Note: A true NL2Cypher fallback would use an LLM, but parameterizing the existing stub safely closes the vulnerability).
2. **Fix Ignored Query Timeout**:
   - The Neo4j async driver `execute_query` accepts the `timeout` kwarg in seconds (not inside a `transaction_config` dict, unless passed as a specific config object). Wait, the modern standard is to use a session with explicit `timeout=5.0`.
   - *Change*: Update the execute call to use `session.run()` with `timeout=5.0` or standard kwargs if `execute_query` supports it directly.
3. **Reconcile Location vs. SubLocation Routing**:
   - In `search()`, after `_resolve_entity_uuid` returns `resolved_uuid`, execute a lightweight probe query:
     `MATCH (e:Entity {id: $uuid})<-[:PART_OF]-(s:SubLocation) RETURN count(s) AS sub_count`
   - If `sub_count > 0`, call `_execute_find_sublocations_for_destination` (passing the `resolved_uuid` or its `name`).
   - If `sub_count == 0`, call `_execute_destination_vibe_summary(resolved_uuid, ...)`.

---

### Clients & Infrastructure (`clients.py`)

#### [MODIFY] [clients.py](file:///Users/rishitagnihotri/bai_internship/GraphRag/src/clients.py)
1. **Fix TLS Verification**: 
   - Change `aiohttp.TCPConnector(verify_ssl=False)` to `verify_ssl=True` (or omit the kwarg to use the safe default).
2. **Support Dynamic Embedding `input_type`**:
   - Update `NvidiaEmbeddingWrapper.embed(self, text: str)` to `embed(self, text: str, input_type: str = "query")`.
   - Ensure the JSON payload uses the passed `input_type` (`"passage"` for data being stored, `"query"` for search retrieval).

---

### Ingestion Pipelines (`ingestion.py` & `ingest_scraped_data.py`)

#### [MODIFY] [ingestion.py](file:///Users/rishitagnihotri/bai_internship/GraphRag/src/ingestion.py)
1. **Embedding Input Types**:
   - When calling `self.embeddings.embed` for inserting new `Alias` nodes and `Claim` nodes, pass `input_type="passage"`.

#### [MODIFY] [ingest_scraped_data.py](file:///Users/rishitagnihotri/bai_internship/GraphRag/src/ingest_scraped_data.py)
1. No major changes, just ensure it correctly calls the updated `ingestion.py` methods.

---

### Database Schema (`setup_neo4j.cypher`)

#### [MODIFY] [setup_neo4j.cypher](file:///Users/rishitagnihotri/bai_internship/GraphRag/setup_neo4j.cypher)
1. **Fix Misleading Comments**: 
   - Update the header comment `4096 dim … nv-embedcode-7b-v1` to `1024 dim ... nv-embedqa-e5-v5` to match reality.

---

### Testing & Verification (`tests/`)

#### [NEW] [test_engine.py](file:///Users/rishitagnihotri/bai_internship/GraphRag/tests/test_engine.py)
- Create unit tests with mocked Neo4j and LLM clients to test the routing logic (`search()`) and ensure that timeouts and parameters are passed correctly to the DB driver.

#### [NEW] [test_ingestion.py](file:///Users/rishitagnihotri/bai_internship/GraphRag/tests/test_ingestion.py)
- Create unit tests for `GraphIngestionPipeline` verifying that deduplication logic works and `input_type` is passed correctly to the embeddings client.

#### [NEW] [test_clients.py](file:///Users/rishitagnihotri/bai_internship/GraphRag/tests/test_clients.py)
- Write tests to verify the SSL flag is enabled by default in `NvidiaEmbeddingWrapper`.

#### [MODIFY] [sample_scraped_data.json](file:///Users/rishitagnihotri/bai_internship/GraphRag/data/sample_scraped_data.json)
- Add a tiny but complete set of valid mock data (1 Island, 1 Region, 1 SubLocation, 1 Attraction) for the `EvaluationHarness` to run an end-to-end fixture if needed.

## Verification Plan

### Automated Tests
- Run `pytest tests/` to ensure engine routing, query parametrization, client instantiation, and ingestion pipelines are robust.

### Manual Verification
1. Attempt a Cypher injection payload directly against the `search` method to verify safety.
2. Confirm destination entities containing SubLocations successfully invoke `_execute_find_sublocations_for_destination`.
3. Confirm general locations without SubLocations route to `_execute_destination_vibe_summary`.
4. Validate that `clients.py` strictly uses `verify_ssl=True` by asserting on the created `aiohttp.TCPConnector`.
