"""Shared test helpers: lightweight fakes that mimic the neo4j async driver's
result shape (`response.records`, each with `.data()`) without a live database."""
from typing import Any, Dict, List, Optional


class FakeRecord:
    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def data(self) -> Dict[str, Any]:
        return self._data


class FakeResponse:
    def __init__(self, rows: List[Dict[str, Any]]):
        self.records = [FakeRecord(r) for r in rows]


class RecordingNeo4j:
    """
    Records every execute_query call and replays canned responses.

    `responder` is a callable (query_text, params) -> list[dict]; defaults to
    returning no rows. Accepts arbitrary kwargs (routing_, database_, ...) so it
    stands in for the real driver's execute_query signature.
    """
    def __init__(self, responder=None):
        self.calls: List[Dict[str, Any]] = []
        self._responder = responder or (lambda q, p: [])

    async def execute_query(self, query, parameters: Optional[Dict[str, Any]] = None, **kwargs):
        text = getattr(query, "text", query)  # unwrap neo4j.Query if used
        timeout = getattr(query, "timeout", None)
        self.calls.append({"text": text, "params": parameters or {}, "kwargs": kwargs, "timeout": timeout})
        return FakeResponse(self._responder(text, parameters or {}))


class RecordingEmbeddings:
    """Records the input_type each embed() call was made with."""
    def __init__(self, vector=None):
        self.calls: List[Dict[str, Any]] = []
        self._vector = vector or [0.1, 0.2, 0.3]

    async def embed(self, text: str, input_type: str = "query"):
        self.calls.append({"text": text, "input_type": input_type})
        return self._vector
