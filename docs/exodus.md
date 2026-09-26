# Exodus — project documentation

> A single document for the team to understand Exodus: what it is, what it is for, how it works,
> what has already been decided and what is missing. It follows the chain of the
> [Architecture Master Playbook](architecture-master-playbook.md) (problem → requirements →
> constraints → drivers → decisions → validation → evolution), with only the sections that apply
> to a command-line tool.
>
> Detailed references: [README](../README.md) (how to run), [CLAUDE.md](../CLAUDE.md)
> (development rules), [ROADMAP](../ROADMAP.md) (history and decisions per item).

---

## 0. Overview

| | |
|---|---|
| **Name** | Exodus |
| **What it is** | A command-line tool (Python) that reads the source code and configuration of legacy systems and generates the documentation to decide their migration to AWS |
| **Project type** | Internal tool supporting modernization/migration *assessments* |
| **Status** | Roadmap 1–13 done (2026-09-25); version `0.1.0` |
| **Where it runs** | On the analyst's machine; nothing is installed system-wide; AI is optional and local (Ollama) |

**In one sentence:** you put the legacy projects in a folder, run one command and get a report
with what exists, how the pieces talk to each other, the risks, what to do with each piece on
AWS and in which order to migrate — every statement pointing to the file and line it came from.

---

## 1. Problem and goals

### Problem

Before migrating a legacy system to the cloud, someone has to answer: *what exists, who talks to
whom, what is tied to what, how much risk there is and where to start*. Today this is done by
hand:

- the legacy documentation does not exist or is out of date;
- the knowledge is in the heads of a few people;
- surveying dependencies (shared databases, queues, calls between systems) across several
  repositories takes weeks and is error-prone;
- the result rarely says *where* each conclusion came from, so it is hard to trust and review.

"Legacy" here is any system about 4 years old or more, or on an unsupported stack: .NET
Framework, .NET Core/.NET 5+, Java, Python; monoliths or microservices (Docker, messaging, NoSQL).

### Goals

1. Cut the survey from days/weeks to minutes, by reading the code itself.
2. Give a **big-picture** view for the decision — not a catalog of details.
3. Make every statement **traceable** (file:line) and therefore reviewable.
4. Recommend the migration path (7R, target AWS service, waves) predictably.
5. Depend on no external service and never send code off the machine.

### How we know it worked

- A single report (`report.html`) that decision makers can read without technical help.
- Every box and arrow in the diagrams points to its source evidence.
- Running again on the same code gives the same result (the AI part uses a cache).
- Validated on real projects: **Pacco** (13 .NET Core 3.1 microservices, Docker, RabbitMQ,
  MongoDB) and **dotnet-billing** (.NET Framework 4.0, WCF, MSMQ, SQL Server).

---

## 2. Scope and context

### In scope

- **Reading:** .NET Framework and .NET Core/5+ (C#), Java (Maven/Gradle, Spring, Java EE) and
  Python (Flask, FastAPI, Django, Celery); `web.config`, `appsettings.json`, `pom.xml`,
  `application.properties`, `Dockerfile`, `docker-compose`, gateways (Ntrada, Ocelot), SQL in
  strings and `.sql` files, Mongo collections.
- **Several inputs together:** projects in different languages analyzed into one graph, to
  reveal how they communicate (called URL ↔ exposed endpoint, shared database, events).
- **Outputs:** HTML report, inventory, risks, migration recommendations, use cases, AS-IS and
  TO-BE diagrams (draw.io) and draft ADRs.

### Out of scope (for now)

- Sending code or data to a cloud AI (the AI is only the local Ollama).
- Effort/cost estimates in numbers (with no calibrated base, it would be a guess dressed as a
  number).
- A method-level call graph (in the backlog; it does not change the big-picture decision).
- Detecting tables through ORMs/frameworks (only what is common to the database type: SQL and
  Mongo).
- Running the migration (Exodus recommends; it does not create infrastructure).

### Context (inputs and outputs)

- **Input:** folders in `exodus-input/` (one per legacy project).
- **Output:** `exodus-output/<project>/` — one project never overwrites another.
- **Optional dependency:** local Ollama (`qwen3.5:9b`). Without it, everything deterministic
  works the same; only the inferred parts are left out (or use the default, in the refactor).

---

## 3. What Exodus does

### Capabilities (functional requirements)

| ID | Capability | How / where it shows |
|---|---|---|
| FR-01 | Identify systems, containers (deployable units) and components | Graph, inventory, C4 diagrams |
| FR-02 | Find databases, queues, external systems and platform services | Inventory, diagrams |
| FR-03 | Link projects to each other: HTTP/SOAP calls, events, gateway, shared database | Diagram arrows, inventory |
| FR-04 | List entry points (routes, queue consumers, jobs, commands) | Inventory |
| FR-05 | List servers, databases and main tables/collections/procedures | Inventory (Data stores section) |
| FR-06 | Point out migration risks with severity | `risks.md`, report |
| FR-07 | Recommend 7R per container, the AWS target of each piece and migration waves | `migration.md`, report |
| FR-08 | Draw AS-IS (L1, L2, L3 of the 3 main containers) | `as-is/c4.drawio`, report |
| FR-09 | Draw TO-BE: replatform (by rule) and refactor (proposed by the AI) | `to-be/*.drawio`, report |
| FR-10 | Record the refactor decisions as ADRs | `to-be/adr/*.md` |
| FR-11 | Describe what each system/container does and the 5 main use cases (AI) | `overview.md`, `use-cases.md` |
| FR-12 | Bring everything together in one page for decision makers | `report.html` |
| FR-13 | Document the analyzed system for the team (this same structure, no diagrams) | `documentation.md` |
| FR-14 | Use the legacy system's written documentation (READMEs, `docs/`) in the business sections, via RAG (a learning example) | `documentation.md`, `rag-trace.md`, Qdrant dashboard |
| FR-15 | Write the documents for people in Brazilian Portuguese (default) or English (`--lang`) | `report.html`, `documentation.md`, `rag-trace.md`, AI texts |

### Properties that matter (non-functional requirements)

| Property | Criterion |
|---|---|
| **Traceability** | Every node and arrow carries `file:line:snippet`; no fact without evidence |
| **Determinism** | The non-AI part always gives the same result for the same code |
| **Privacy** | No code leaves the machine; the AI receives only extracted facts (and, for use cases, excerpts of the project's own files, locally) |
| **Time** | Without AI: seconds. With AI, first run on Pacco: ~3–5 min; after that, cache |
| **Cost** | Zero: no paid services; local AI |
| **Output portability** | `report.html` opens offline, with no server, and can be emailed |
| **Maintainability** | Coverage ≥ 80% in domain and application (currently ~99%), `mypy --strict`, `ruff` |

---

## 4. Constraints, assumptions and dependencies

**Constraints**
- Python 3.12, `uv` package manager; runs from inside the project folder (not an installable
  package).
- Local AI only (Ollama); no external LLM API.
- Minimal runtime dependencies: `pydantic`, `tree-sitter`, `tree-sitter-language-pack`,
  `typer`. Any new one needs a reason (e.g. the report's Markdown converter was written by hand
  to avoid adding one).

**Assumptions** (true until proven otherwise)
- The source code is available and complete enough (cloned repositories; `.sln` solutions that
  point to missing projects produce a warning).
- Configuration (connection strings, URLs, queues) lives in repository files — secrets injected
  only at runtime do not show up.
- The migration keeps the existing integrations (who calls whom) — the basis of the TO-BE
  replatform.

**Dependencies**
- Ollama with the `qwen3.5:9b` model for the inferred parts (optional).
- RAG (optional): the `bge-m3` model in Ollama and Qdrant in Docker (`docker-compose.yml`).
- draw.io (web app, desktop or extension) to open the `.drawio` files — the HTML report does not
  need it.

---

## 5. What drives the architecture (drivers)

| ID | Driver | Effect on the architecture |
|---|---|---|
| AD-01 | **Evidence is non-negotiable** | Extractors emit *facts with evidence*, never loose nodes; the graph keeps the evidence on every element |
| AD-02 | **Deterministic before AI** | Everything that can be deduced is a testable rule; the AI only interprets what was already extracted and is marked as *inferred* |
| AD-03 | **Many languages and formats** | A single port (`FactExtractor`); adding a reader = new adapter + one line in `main.py` |
| AD-04 | **Big-picture view** | Documents are direct lists of what changes the decision; detail stays in `graph.json` |
| AD-05 | **Privacy and zero cost** | Local AI through Ollama, with a cache; prompts carry only extracted facts |
| AD-06 | **Output reviewable by people** | Diagrams with their own layout (arrows do not cross boxes), ADRs with status "Proposed", report in the reader's language |

---

## 6. Principles

- **Clean Architecture:** dependencies point inward. `domain` knows nothing about files,
  tree-sitter, the CLI or LLMs (Pydantic is the only exception, by a conscious decision).
- **SOLID / Open-Closed:** a new language, format or output = a new adapter; do not change what
  exists.
- **DRY:** walking the tree-sitter tree lives in one place; so does URL/connection string
  normalization; the AWS options catalog is the single source for the LLM and for validation.
- **KISS:** no speculative abstraction; no DI framework (manual composition in `main.py`).
- **Big picture:** when planning a feature, the simplest version that delivers the overall view.

---

## 7. Main decisions (and why)

Each decision with its reason, what is lost (trade-off) and the consequence. The full history is
in the [ROADMAP](../ROADMAP.md), item by item.

| # | Decision | Why | Trade-off / consequence |
|---|---|---|---|
| D-01 | Pydantic allowed in the domain | Validation, JSON and the JSON Schema of `graph.json` come from the same definition | The domain is not 100% pure; a field change = `SCHEMA_VERSION` bump (currently 1.5) |
| D-02 | One `Node` with `NodeKind` instead of a class per type | A graph that is simple to walk and serialize | Per-type rules live in functions, not in polymorphism |
| D-03 | Extractors emit **facts**; `build_graph` (pure) builds the graph and the links between projects | An extractor sees one file; linking projects needs all of them | One more step, but testable without IO |
| D-04 | Container = deployable unit; libraries are part of whoever uses them; tests stay out | That is what actually migrates | Pacco: 41 projects → 13 containers |
| D-05 | Database = a single arrow ("reads/writes"); tables only in the inventory | Readable diagram | Reads and writes are not separated |
| D-06 | Tables/collections only through patterns common to the database type (SQL, Mongo), never ORMs | A generic, predictable rule | Projects that only use a framework (e.g. Convey in Pacco) get no collection list |
| D-07 | Migration recommendations **by rules only** (7R, targets, waves) | The weightiest decision must be predictable and evidenced | Cases with no rule show as "No rule: evaluate" |
| D-08 | 7R (AWS's current official list), with **two paths** per container: fast and modern | AWS recommends migrating first and modernizing later; both stay visible | Retain, Repurchase and Relocate only in the legend (they cannot be deduced from code) |
| D-09 | Waves = foundation (platform) + topological levels; a shared database ties pieces together; callees before callers | Minimizes cloud → datacenter traffic during the migration | Events do not order waves (the broker goes in the foundation) |
| D-10 | Refactor **proposed by the AI**, choosing only from the catalog `exodus/catalog/refactor-catalog.json`, prioritizing cost → security → performance | The refactor needs judgment; the closed list avoids made-up services and allows validation | 9B model: rationales are sometimes imprecise and confidence too high → ADRs come out "Proposed" |
| D-11 | No effort estimate | Without calibration, a number misleads | Decision makers estimate from the risks and waves |
| D-12 | Self-contained HTML report, own SVG diagrams, texts in Brazilian Portuguese by default or English (`--lang en`) | One file that can be emailed and opens offline, in the reader's language | No official AWS icons in the HTML (they are in the `.drawio` files) |
| D-13 | No MCP server | The audience reads documents; assistants already read `graph.json` directly | Reconsider only if a graph gets too big |
| D-14 | RAG only as an example, over the legacy's written documentation: Qdrant + `bge-m3`, local and license-free | Learn the technique on a real case (unstructured text that does not fit in the prompt) without touching what is deterministic | One more optional piece (Docker); quality depends on the documentation and its language — hence `rag-trace.md` |

---

## 8. How it works

Processing is a sequence of steps, each with one responsibility:

1. **Read (`scan_projects`)** — walks the input folders (skipping `bin`, `obj`,
   `node_modules`…) and hands each file to the extractors that recognize it.
2. **Extract facts (`FactExtractor`)** — each adapter reads one kind of file (C#, Java, Python
   through tree-sitter; `web.config`, `appsettings.json`, `pom.xml`, Docker, gateways, SQL…) and
   emits facts with evidence: "project X declared", "connection string Y", "route /orders",
   "publishes OrderCreated".
3. **Build the graph (`build_graph`, pure)** — turns facts into systems, containers,
   components, databases, queues, external systems and platform, and links projects to each
   other. Deterministic IDs (`container:<system>/<project>`, `datastore:<engine>:<host>/<db>`).
4. **Infer (optional, Ollama)** — the description of each element, the 5 main use cases and the
   refactor proposal. Everything is marked as inferred, with confidence, and cached
   (`*-cache.json`); an invalid answer is discarded or falls back to the default.
5. **Write** — `graph.json` (with `graph.schema.json`) and the Markdown documents.
6. **Draw (`render`)** — C4 views computed in the domain → own layout (columns by dependency,
   databases at the bottom, arrows that do not cross boxes) → draw.io (AS-IS and TO-BE), ADRs and
   the HTML report.

### Code organization

| Layer | Folder | What it holds |
|---|---|---|
| Domain | `exodus/domain/` | Graph model, facts, identity (URLs, connection strings), C4 views, risks, migration (7R and waves), TO-BE and refactor — rules only, no IO |
| Application | `exodus/application/` | Ports (Protocols) and use cases: read, build the graph, infer, write use cases, propose the refactor, draw |
| Infrastructure | `exodus/infrastructure/` | Code/config readers, Ollama, JSON persistence, renderers (draw.io, SVG, Markdown, HTML), catalog |
| Interface | `exodus/interfaces/cli/` | `typer` commands and writing the files |
| Composition | `exodus/main.py` | The only place that knows every adapter |
| Catalog | `exodus/catalog/refactor-catalog.json` | AWS options per piece type (26 types, 86 options) — a new service = a new entry, not code |

---

## 9. How to use it

```bash
uv run python -m exodus                  # choose projects from ./exodus-input/ → analysis + diagrams + report
uv run python -m exodus --lang en        # the same, with the documents in English
uv run python -m exodus scan <folder>    # analysis only
uv run python -m exodus render --as-is --to-be   # diagrams and report only
```

The terminal shows the progress of each step and, at the end, the total time. Step by step and
first-time setup in the [README](../README.md).

### What comes out in `exodus-output/<project>/`

| File | Contents |
|---|---|
| `report.html` | **Start here**: summary, AS-IS, high risks, migration, TO-BE and collapsed details |
| `documentation.md` | Documentation of the analyzed system, in this same structure (sections 0–14), no diagrams |
| `rag-trace.md` | What RAG retrieved for each question and what the AI wrote with it (only with Qdrant running) |
| `migration.md` | 7R per container (two paths), the AWS target of each piece, waves |
| `risks.md` | Risks with severity and evidence |
| `inventory.md` | Containers, packages, endpoints, entry points, databases and tables, queues, external systems, platform, messaging |
| `overview.md`, `use-cases.md` | What each piece does and the 5 main use cases (inferred) |
| `as-is/c4.drawio` | C4 L1, L2 and L3 (3 main containers per system) |
| `to-be/replatform.drawio`, `to-be/refactor.drawio`, `to-be/adr/` | Architecture on AWS (fast and modernized) and the decisions |
| `graph.json` | Everything, with evidence (format in `graph.schema.json`) |

---

## 10. How we validate

- **TDD** in the domain and use cases; integration tests against mini legacy projects in
  `tests/fixtures/` (tiny-shop, micro-services, java-shop, python-shop…).
- **Quality gate** on every slice: `pytest` (coverage ≥ 80%, currently ~99%, 389 tests),
  `ruff` and `mypy --strict` with no errors.
- **Tests never call the model** (Ollama is simulated as unavailable), so they are fast and
  deterministic.
- **Validation on a real project** for every feature (Pacco and dotnet-billing): several
  problems only showed up there — weak use case ranking, false WCF in `GrpcServiceHost`,
  gateways as Retire candidates, APIs classified as workers, an unreadable diagram in the report.

---

## 11. Risks, limitations and technical debt

| Item | Impact | What to do |
|---|---|---|
| Small local model (9B): rationales sometimes imprecise, confidence too high | Refactor and use cases need human review | ADRs come out "Proposed"; everything is marked as inferred |
| HTTP routes of some frameworks (Convey minimal APIs) do not become entry points | Fewer possible use cases | A container called over HTTP is already treated as an API; a new reader if it becomes a priority |
| Collections declared only through a framework (Convey `AddMongoRepository`) do not show up | Incomplete data inventory in those projects | Conscious decision (D-06); one regex line if needed |
| A plain string starting with "Select … from" can become a false table | Rare; it shows with evidence | Accepted for simplicity |
| The report's detail sections reuse the `.md` files, which are always in English | A report in Portuguese has sections in English | Translate those `.md` files if the audience asks |
| Containers with no relationship stack in a single column of the diagram | Taller diagram | Backlog: group them in a grid |
| Secrets injected only at runtime are not seen | Secret risks may be missing | Documented assumption (section 4) |

---

## 12. Evolution

**Done (roadmap items 1–13):** draw.io finish; .NET Core and microservices; Java and Python;
entry points; risks; AI base and descriptions; use cases; data (servers, databases, tables,
procedures); migration recommendations (7R and waves); TO-BE and ADRs; HTML report;
documentation of the analyzed project (`documentation.md`); RAG example over the legacy's
written documentation; document language option (`--lang pt-br|en`).

**Backlog (added when needed):**
- A method-level call graph (deterministic steps for the use cases).
- Group containers with no relationship in a grid in the layout.

New features follow the flow in `CLAUDE.md`: plan → approval → TDD → tests/lint/mypy → docs, in
small slices, validated on a real project.

---

## 13. Open questions

| ID | Question | Impact |
|---|---|---|
| Q-01 | What is the next roadmap item? (items 1–13 done) | Project direction |
| Q-02 | Should the `.md` files that are always in English (inventory, risks, migration, ADRs) also follow `--lang`? | Report consistency in Portuguese |
| Q-03 | Do we need a bigger model (beyond the current 8 GB of GPU) for the refactor? | Quality of the rationales |
| Q-04 | Which real projects besides Pacco and billing should serve as validation references (especially with SQL and procedures)? | Confidence in the data rules |

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **Legacy** | A system about 4 years old or more, or on an unsupported stack |
| **Evidence** | `file:line:snippet` a fact was taken from |
| **Fact** | Something an extractor found in a file (e.g. "connection string"), before it becomes the graph |
| **Graph** | Systems, containers, components, databases, queues, external systems and platform, with their links (`graph.json`) |
| **System / Container / Component** | C4 levels: analyzed folder / deployable unit / project or namespace inside it |
| **Platform** | Shared infrastructure services (Consul, Vault, Jaeger, Seq, RabbitMQ…) |
| **C4 (L1, L2, L3)** | Diagram model: context, containers, components |
| **AS-IS / TO-BE** | Current architecture / architecture on AWS |
| **7R** | AWS migration strategies: Retire, Retain, Rehost, Relocate, Repurchase, Replatform, Refactor |
| **Fast / modern path** | Rehost or Replatform (reach AWS changing little) / Refactor (rewrite what is needed) |
| **Wave** | A group of pieces that migrates together; wave 0 is the foundation (platform) |
| **Refactor catalog** | A closed list of AWS options per piece type, used by the AI and by validation |
| **Inferred** | Produced by the AI from extracted facts; always with confidence and marked as such |
| **ADR** | Architecture Decision Record: context, options, decision and consequences |
