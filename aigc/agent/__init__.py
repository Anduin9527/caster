"""Agent module: retrieval, sessions, planning, approval and the model connection.

Module boundaries follow plan section 8:

* :mod:`contracts`  - the four cross-layer objects (M0).
* :mod:`settings`   - private model connection config and connection testing.
* :mod:`retrieval`  - SearchHit producers; exact/token search now, RAG later.
* :mod:`sessions`   - conversations, messages and runs in the business SQLite.
* :mod:`intent`     - natural language to structured ProductionIntent.
* :mod:`planner`    - intent + context to a frozen GenerationPlan.
* :mod:`tools`      - the agent's read-only and prepare tools (never approve).
* :mod:`engine`     - run lifecycle, events, LlamaIndex backend + test double.
* :mod:`authorize`  - the approval transaction and idempotent enqueue.
* :mod:`router`     - the ``/agent`` HTTP surface.
"""
