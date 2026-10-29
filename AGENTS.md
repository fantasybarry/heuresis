# Code-context workflow

Use SDL-MCP as the primary code-retrieval tool in this repository. For a known file or symbol, use exact SDL retrieval or a focused `sdl.context` request. Start multi-symbol context around 3,000 tokens; expand for specific missing evidence. Read sufficient current source before changing implementation.

Use Graphify when documentation relationships or unresolved cross-module structure matter. Start with one query around 1,000 tokens, then carry only relevant repository-relative paths, symbol names, constraints, and source references into SDL. Do not repeat broad discovery in both tools or automatically load the full graph or `GRAPH_REPORT.md`. Use `graphify path` or `graphify explain` for a focused relationship or concept.

Reuse unchanged SDL context. After compaction or agent handoff, recover missing bodies with `refsMode: "off"` instead of relying on references alone. Use digest output for tests and builds, then inspect detailed logs when needed. Treat omitted results as unknown. If an index is stale or lacks coverage, verify the current source with targeted reads. Correctness takes priority over the initial budgets.

When the user invokes `/graphify`, follow the installed Graphify skill. After modifying code, run `graphify update .` to keep the existing project graph current.
