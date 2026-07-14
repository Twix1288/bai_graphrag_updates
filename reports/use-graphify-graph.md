---
name: use-graphify-graph
description: "For codebase questions in GraphRag, query the graphify graph first to save tokens"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a815e3ba-3b96-41d8-9d6f-d7533be1f89f
---

For this project, always use the graphify knowledge graph at `graphify-out/graph.json` to answer codebase/architecture questions instead of grepping or reading source files broadly.

**Why:** The user explicitly asked to lean on the graph to save tokens; it returns a scoped subgraph far smaller than raw source browsing.

**How to apply:** Run `<python> -m graphify query "<question>"` (the CLI `graphify` is not on PATH — use `$(cat graphify-out/.graphify_python) -m graphify ...`). Use `path "A" "B"` for relationships and `explain "X"` for a concept. Only open source files to confirm a specific detail the graph surfaced. Note the current graph is a `--code-only` build, so the 15 docs are not in it.
