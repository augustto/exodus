# Exodus

A tool that reads legacy projects — any system about 4 years old or more, or on an unsupported
stack: .NET Framework and .NET Core/.NET 5+, Java, Python; monoliths or microservices (Docker,
messaging, NoSQL) — and generates the documentation that supports the decision to migrate to AWS:
AS-IS C4 diagrams (and TO-BE), inventory, dependencies, risks and recommendations. The input can be
several projects in different languages, analyzed together to reveal how the systems communicate.

## Stack
- Python 3.12+ (pinned to 3.12 via `.python-version`), `uv` package manager
- CLI `typer`; parsing `tree-sitter` + `tree-sitter-language-pack`; serialization `pydantic` v2
- Quality: `ruff` (lint + format), `mypy --strict`, `pytest`; use `pytest-cov` when coverage
  helps investigate a gap
- Output: draw.io (`as-is/c4.drawio`, one page per C4 view). Geometry in `rendering/layout.py`
  (layered layout + routing of arrows that neither cross boxes nor overlap); the evidence goes on
  each element/arrow

## Commands
```
uv run pytest                            # focused behavior and integration tests
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict exodus
uv run python -m exodus                  # choose projects from ./exodus-input/ → scan together + render
uv run python -m exodus --lang en        # the same, documents for people in English (default pt-br)
uv run python -m exodus scan <path>      # writes to ./exodus-output/<folder-name>/ (-o changes the folder)
uv run python -m exodus render --as-is   # renders each project in ./exodus-output/*/
uv run python -m exodus render --to-be   # TO-BE (AWS) of each project in ./exodus-output/*/
```

## Principles (mandatory)
- **Clean Architecture**: dependencies point inward. `domain` knows nothing about tree-sitter,
  files, the CLI or LLMs (pydantic is the only exception — see decisions).
- **SOLID**: each language/config reader is a `FactExtractor` adapter. Adding a language = new
  adapter + one line in `main.py`; never change existing code (Open/Closed).
- **DRY**: walking the tree-sitter tree lives in `TreeSitterExtractor` (each language only
  provides queries); URL/connection string normalization lives in `domain/identity.py`.
- **KISS**: no speculative abstraction; an interface only with real use. No DI framework — manual
  injection in `main.py` (composition root). If something conflicts with KISS, point it out and
  propose the simplest option.
- **Big-picture view (generated documents)**: every document serves the migration decision and
  must give the overall view: direct lists of what matters to decide (what exists, where it is,
  who uses it, how much it weighs). Detail that does not change a decision (methods, columns,
  technical step by step, plumbing) stays out of the `.md` files/diagrams; at most in
  `graph.json`. When planning a feature, pick the simplest approach that delivers this view and
  cut the rest.
- **Language**: code, identifiers, comments, docstrings and the repository docs are in English.
  The documents for people (`report.html`, `documentation.md`, `rag-trace.md`) and the AI texts
  follow `--lang` (`pt-br` by default, or `en`): fixed texts via `pick(language, pt_br, en)` in
  the renderers, the domain writes no sentence in a language (it returns structured data, e.g.
  `OpenQuestion`). The other outputs (inventory, risks, migration, ADRs, diagrams) are in English.

## Architecture decisions
- **Pydantic is allowed in the domain** (a conscious decision, trading purity for practicality):
  entities, facts and value objects inherit `Entity` (frozen `BaseModel`, `extra="forbid"`) and
  use keyword arguments. Field rules (line >= 1, non-empty evidence) are `Field(...)` and raise
  `ValidationError`; aggregate invariants (`ArchitectureGraph`) raise `DomainError`. The format
  of `graph.json` is `GraphDocument`; a field change in an entity = `SCHEMA_VERSION` bump. No
  other external library enters the domain.
- **One `Node` with `NodeKind`** (SYSTEM, CONTAINER, COMPONENT, DATA_STORE, QUEUE, EXTERNAL_SYSTEM,
  PLATFORM) instead of one class per type. `Relationship` with `RelKind` (calls, reads, writes,
  publishes, consumes, depends_on).
- **Extractors emit facts** (`domain/facts.py`), not nodes. `build_graph` (pure) turns facts into
  an `ArchitectureGraph` and links projects to each other (called URL ↔ exposed endpoint, shared
  database). Node IDs are deterministic (`container:<system>/<proj>`,
  `datastore:<engine>:<host>/<db>`).
- **A single `FactExtractor` port** for source code and config (same signature: file → facts).
- **Database = `depends_on`** labeled "reads/writes" (a single arrow, reads and writes not
  separated). Tables, collections and procedures come only from what is common to the database
  type (SQL in strings/`.sql`, Mongo collections), never from ORMs/frameworks, and appear in the
  inventory, not in the diagrams.
- **Evidence is non-negotiable**: every node and edge carries `Evidence(file, line, snippet)`. No
  fact without evidence; every arrow in the diagram must be traceable.
- `graph.json` has `schema_version`; `graph.schema.json` is generated with it.
- **Generated C4 levels (rule)**: every render always generates L1 (Context), L2 (Container, one
  per system) and L3 (Component, traditional format: one diagram per container showing its
  components) only for the **top 3 core containers of each system** — a deterministic ranking
  computed in the domain (do not generate L3 for every container).
- **Use cases (rule)**: only for the **5 main entry points of each system** (`core_entry_points`
  in the domain, containers taking turns by centrality). The AI (Ollama) only writes; the
  `write_use_cases` use case picks the files and drops any step whose file:line citation is not
  in what was sent.
- **Migration recommendations (rule)**: only through deterministic rules in the domain
  (`domain/migration.py`), no AI: 7R (never 6R) with two paths per container (fast and modern),
  a table of AWS targets per piece type ("No rule: evaluate" when none covers it) and waves
  (foundation → topological levels). No effort estimate.
- **TO-BE (rule)**: replatform is deterministic (the rules of item 9); the **refactor is proposed
  by the AI**, prioritizing cost → security → performance, but only choosing options from the
  catalog `exodus/catalog/refactor-catalog.json` (single source, passed to the LLM and used to
  validate the answer). Every choice is marked as inferred, with a rationale; every arrow comes
  from an AS-IS relationship. A new AWS service = a new catalog option, not code.
- **Project documentation (rule)**: `documentation.md` follows the structure of `docs/exodus.md`
  (playbook in `docs/architecture-master-playbook.md`). Only problem/goals, principles,
  assumptions and glossary come from the AI (marked *inferred*, principles citing a fact that was
  sent); the rest comes from the graph.
- **RAG (learning example)**: the legacy's written documentation (text) → pieces → `bge-m3`
  (Ollama) → Qdrant (`docker-compose.yml`, REST through the standard library). Ports
  `EmbeddingModel`, `VectorStore`, `Retriever`; pieces never enter `graph.json`; optional
  (without Qdrant, warn and go on); every use leaves a trace in `rag-trace.md`.
- **Element placement (rule, classic C4, the same in L1/L2/L3)**: systems/containers/components
  in columns by dependency (callers on the left), inside the boundary in the zoomed-in view;
  whoever only calls the boundary sits to its left, other externals to the right (in L1, external
  systems in the rightmost column); databases and queues in a band at the bottom, under the
  column of whoever uses them — inside the boundary when they belong to the system, below it when
  shared. Arrows never cross boxes nor overlap; an arrow to a database/queue enters from the top.
- **Container = deployable unit** (Web/Worker SDK, `Exe`, web/WCF project); libraries are part of
  the applications that reference them; tests stay out (noted on the tested container).
  Components: in a service with several projects, one per project; in a single project,
  namespaces one level below the root.
- **Messaging**: a direct arrow from publisher to consumer (exchange owner → subscriber; gateway
  command/route → exchange owner; without exchange routing — MassTransit, NServiceBus — whoever
  publishes the type → whoever consumes the type), with the message names. **Platform**
  (`NodeKind.PLATFORM`): its own group in L2, connected by a single line to the boundary; out of
  L1 and L3. Caches (Redis) stay out of the diagrams (inventory only). Calls, data and events stay
  together on a single L2 page.

## Structure
```
exodus/            (run from the project folder: `python -m exodus`; not an installable package)
  domain/            model.py, facts.py, identity.py, graph.py   (pydantic only)
  application/       ports.py (Protocols), use_cases/ (scan_projects, build_graph, render_diagrams)
  infrastructure/    filesystem.py, parsing/ (tree-sitter + url literals), config/ (web.config,
                     csproj, .sln, packages.config, .svc/.aspx, appsettings.json, Ntrada/Ocelot
                     gateways, Dockerfile/docker-compose, …), persistence/ (JSON), rendering/
                     (layout.py, draw.io, inventory.md)
  interfaces/cli/    typer commands (they do the IO of writing the output)
  main.py            composition root
tests/ unit/ integration/ fixtures/   (mini legacy projects that talk to each other)
```

## Scope
- **Phase 1 (current)**: `exodus scan` (language detection, inventory, deterministic extraction
  via tree-sitter and config, unified graph with relationships between projects) and
  `exodus render --as-is` (C4 L1 + L2 + L3 of the top 3 core containers of each system, in
  draw.io). Output in `./exodus-output/<project>/` (name of the analyzed folder; several paths in
  the same scan → sorted names joined by `+`), so one project does not overwrite another:
  `graph.json`, `report.html`, `documentation.md`, `inventory.md`, `risks.md`, `migration.md`,
  `overview.md`, `use-cases.md`, `rag-trace.md` (with Qdrant running), `as-is/`, `to-be/`.
- **Out of scope for now** (do not implement): enrichment with Claude (Agent SDK/MCP; the AI is
  only the local Ollama), effort scoring/estimates, call graph, web API. They must come in as new
  adapters/use cases (e.g. a new data source = a new `FactExtractor`; TO-BE = a use case over the
  graph + renderer).
- **Roadmap**: next features in priority order in `ROADMAP.md`; follow the order.

## Quality and workflow
- Test observable behavior and regressions that matter for the migration decision. Prefer a
  representative integration test over repeated assertions at every layer; do not add tests for
  trivial formatting, model-library behavior or reversible low-impact changes.
- Use `tests/fixtures/` for cross-language and end-to-end behavior. Coverage is diagnostic, not a
  target; `ruff` and `mypy --strict` must have no errors.
- Before coding something new: present a plan and wait for approval.
- Small vertical slices (one language end to end at a time). At the end of each slice: run
  tests, lint and mypy and show the result.
