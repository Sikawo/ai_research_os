# Scientific Serendipity Synthetic Regression Suite

All fixtures in this directory are invented for deterministic policy testing.
They contain no private, unpublished, application-specific, or externally
retrieved research content. The suite spans biological, ecological, materials,
control-system, and distributed-computing examples to avoid domain overfitting.

Each numbered case maps to the approved Scientific Serendipity acceptance suite.
The fixtures state the input condition, expected scientific/firewall/analogy or
action outcome, and the invariant protected by that outcome. They are contract
fixtures, not claims that a language model semantically solved an experiment.

Run with:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_scientific_serendipity_contract.py
```

No external model, API, network, literature search, embedding service, or
private-memory access is required.
