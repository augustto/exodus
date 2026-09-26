# Exodus Roadmap

Final goal: **support the decision to migrate legacy systems to AWS** — what exists, what each
system does, how much it costs/risks to migrate and where each piece goes.

Ordering criterion: first what brings us closest to that decision with the least risk, respecting
the dependencies between features. A deterministic base (traceable, testable, free) before AI;
AI comes in to interpret what the parser already found, always citing evidence and marked as
*inferred*.

Each item is a vertical slice: plan → approval → implementation → focused tests/lint/mypy → docs.

**Big-picture view (rule for every item):** each generated document gives the overall view for
deciding, in direct lists; detail that does not change a decision stays out. When planning an
item, prefer the simplest version that delivers that (e.g. item 8 = servers, databases, main
tables and procedures by name, not a call graph nor columns).

| # | Feature | Delivers | AI? | Size |
|---|---|---|---|---|
| 1 | ✅ draw.io finish | readable diagrams with no manual adjustment | no | S |
| 2 | ✅ .NET Core/.NET 5+ and microservices | Pacco and similar: services, databases, queues/events and calls between services | no | L |
| 3 | ✅ Reading Java and Python | the same graph/diagrams/inventory for Java and Python projects | no | L |
| 4 | ✅ Entry points (.NET, Java, Python) | a reliable list of what triggers each flow | no | M |
| 5 | ✅ Risk report | `risks.md` | no | M |
| 6 | ✅ AI base + descriptions | `overview.md`, a description in each box | yes | M |
| 7 | ✅ Use cases | `use-cases.md` | yes | M |
| 8 | ✅ Data: servers, databases, tables and procedures | data section in `inventory.md` | no | M |
| 9 | ✅ Migration recommendations | `migration.md` (7R, AWS mapping, waves) | no | L |
| 10 | ✅ TO-BE + ADRs | `to-be/replatform.drawio`, `to-be/refactor.drawio`, `adr/*.md` | yes | M |
| 11 | ✅ HTML report | a single page for stakeholders | no | M |
| 12 | ✅ Project documentation | `documentation.md` (playbook structure) | partial | M |
| 13 | ✅ RAG example: the legacy's written documentation | business sections based on the documents; `rag-trace.md` | yes | M |
| 14 | ✅ Document language | `--lang pt-br|en` for the documents for people; code and repository docs in English | no | S |

> **Legacy** = any system about 4 years old or more, or on an unsupported stack: .NET Framework
> and also .NET Core/.NET 5+, Java, Python; monoliths or microservices (Docker, messaging,
> NoSQL). .NET Framework and .NET Core/microservices are read (item 2); Java/Python come in
> item 3, before AI. From item 4 on, each feature applies to all the legacy code that is read.

---

## 1. ✅ draw.io finish (done on 2026-09-24)
**Why now:** it is almost there; it closes phase 1 with presentable diagrams.
- Minimum spacing between the exits of a box (the box grows when there are many arrows).
- A corridor wide enough for the arrow text; long texts break into two lines.
- Fewer detours and crossings (arrow slots near the straight line, more ordering passes).
- Tied databases/queues spread across the columns of whoever uses them.
- Title and legend (colors/shapes) on each page.
- Cleanup of the old output (`.mmd`, `.dsl`, `.excalidraw`) — with confirmation.

## 2. ✅ .NET Core/.NET 5+ and microservices (done on 2026-09-24)
**Why now:** it is legacy too (e.g. Pacco, .NET Core 3.1 from 2019, unsupported since 2022) and
today it comes out with an empty graph or no relationships. Microservices integrate through
events and config, not through `web.config`.
- **Warning** when a project has nothing recognizable (today Exodus generates empty diagrams
  without warning) and when the solution references missing projects (e.g. a `.sln` pointing to
  sibling repos that were not cloned).
- `appsettings*.json`: `ConnectionStrings`, MongoDB, Redis, RabbitMQ/Kafka/Azure Service Bus,
  URLs and the HTTP service map (e.g. Convey's `httpClient.services`), per environment.
- Messaging as integration: published and consumed messages/events (Convey `[Message]`,
  MassTransit, NServiceBus, `IBusPublisher`/`ICommandHandler`/`IEventHandler`), linking the
  publishing service to the consumers, through the exchange/queue (a new relationship type per
  event).
- `docker-compose*.yml` and `Dockerfile`: services, infrastructure images (Mongo, RabbitMQ,
  Redis, Consul, …), environment variables and runtime version as source and evidence.
- Service discovery/gateway (Consul, Fabio, Ocelot/NTRADA): gateway routes → service.
- A minimal microservices fixture (2–3 services, one event, one NoSQL database) and validation
  on the full Pacco (clone the 11 repositories into `exodus-input/Pacco/`).
- **Decisions (2026-09-24):** events show as a **direct asynchronous arrow** from publisher to
  consumer, with the events in the text and "(RabbitMQ)"; the broker shows once as
  infrastructure. **Platform services** (Consul, Fabio, Vault, Jaeger, Seq, Prometheus, Grafana)
  show **in the diagrams** grouped in **their own rectangle**, with **a single line** linking
  that group to the area (boundary) of the core systems; which service uses which tool stays in
  the inventory.
- **Slices:** ✅ 2a container = deployable unit (+ warnings; Pacco: 41 → 13 containers); ✅ 2b
  `appsettings.json` (databases, broker, HTTP calls by service name, platform); ✅ 2c events
  (Convey); ✅ 2d gateways (Ntrada, Ocelot); ✅ 2e Docker (`Dockerfile`, `docker-compose`).
- ✅ Warning when a system with several containers shows no communication; components =
  project/layer in services with several projects, namespace one level below the root in a
  single project (Pacco: 213 → 55 components; L3 of a layered service with 4 boxes).
- ✅ Mutual imports (A↔B) as a single double-headed arrow; Platform group in L2.
- ✅ L2 readability: caches (Redis) out of the diagrams; messages shown together with calls and
  data on the same page.
- ✅ Events exchanged both ways in a double-headed arrow (Pacco: 19 → 16 arrows, loops underneath
  12 → 8); MassTransit/NServiceBus linked by message type; Docker (runtime image per container,
  compose services in the inventory).
- **Out of scope (consciously):** dynamic subscriptions through a project's own file (Pacco
  Operations, `messages.json`) — a project-specific convention, not a library's.
- **Layout (pending, moved to the Backlog at the end of this file):** containers with no
  relationship stack in a single column; group the loose ones in a grid.

## 3. ✅ Reading Java and Python (done on 2026-09-25)
**Why now:** Java and Python are among the legacy systems to analyze; without reading them,
nothing else applies to those systems. One language at a time, end to end (Java, then Python).
- ✅ Java (done on 2026-09-24): `pom.xml`/`build.gradle` (container, Java version,
  dependencies), `application.properties`/`.yml` (JDBC and HTTP URLs), tree-sitter for packages,
  classes and imports (components); basic Spring MVC/JAX-RS endpoints. From `web.xml` only the
  servlets are read (item 4); `persistence.xml` and JNDI/datasources are left for a
  complementary slice, when a fixture or real project brings them as a need (a prerequisite of
  the "unresolved datasources" rule of item 5).
- ✅ Python: `requirements.txt` and `pyproject.toml`/`setup.py`/`Pipfile` (container, version,
  packages), `settings.py` (database URLs and SQLAlchemy via `DATABASE_URL`) and YAML;
  tree-sitter for modules, classes and imports; HTTP URLs; basic Flask, FastAPI and Django
  endpoints.
- New `FactExtractor` adapters + one line in `main.py` (Open/Closed); a minimal fixture of its
  own per language; links between projects in different languages (called URL ↔ exposed
  endpoint, shared database) already come from `build_graph`.

## 4. ✅ Entry points (.NET, Java, Python) (done on 2026-09-25)
**Why now:** it is the base of the use cases (item 7) and of the effort estimate (item 9).
Deterministic and traceable.
- ✅ .NET: WCF operations (`[OperationContract]`), `.svc`/`.asmx`/`.aspx`/`.ashx` pages,
  MVC/Web API controllers (routes), queue consumers, Windows Services and `IJob`/`Timer` jobs.
- ✅ Java: servlets (`web.xml`, `@WebServlet`), Spring controllers (`@RequestMapping`,
  `@GetMapping`…), JAX-RS (`@Path`), JAX-WS (`@WebService`), JMS listeners (`@JmsListener`) and
  `@Scheduled` tasks.
- ✅ Python: Flask/FastAPI routes (`@app.route`/`@app.get`…), Django (`urls.py`), Celery tasks
  (`@task`/`@shared_task`), APScheduler jobs (`@scheduled_job`, `add_job`), pika/RabbitMQ
  consumers (`basic_consume`) and Django commands (`management/commands/*.py`). Out of scope for
  now (KISS, no fixture/real project asking for it): Kafka, RQ/Dramatiq, the `schedule` library
  and CLI frameworks other than Django.
- ✅ New `EntryPoint` fact (kind, route/name, container, evidence) + a section in `inventory.md`.

## 5. ✅ Risk report (`risks.md`) (done on 2026-09-25)
**Why now:** high value for the decision, no AI, uses what is already extracted.
- ✅ Deterministic rules with evidence and severity:
  - .NET: unsupported runtime (.NET Framework 4.0–4.6.1, .NET Core 1.x–3.1, .NET 5/6/7),
    technologies with no equivalent in current .NET (WCF, MSMQ, Web Forms, Remoting), abandoned
    libraries (e.g. Convey, old MassTransit versions);
  - Java: unsupported version (Java 6/7/8), legacy Java EE/`javax` (EJB, JSF, JAX-WS), coupled
    application server (WebLogic, WebSphere, old JBoss);
  - Python: Python 2 or unsupported 3.x, frameworks in unsupported versions (old Django/Flask);
  - all: database shared between systems (coupling), secrets in config, old packages,
    unresolved datasources (in Java it depends on reading JNDI/`persistence.xml`, still pending
    — see item 3; without it, the rule applies only to .NET/config).
- ✅ Each rule = one item of a list (easy to extend); summary per system/container.

## 6. ✅ AI base + descriptions (done on 2026-09-25)
**Why now:** it prepares the whole AI layer with a small, visible delivery.
- ✅ `Enricher` port (application) + local Ollama adapter (infrastructure) + use case; nothing in
  the domain.
- ✅ Provenance: *extracted* × *inferred* fact (with confidence); `SCHEMA_VERSION` 1.3.
- ✅ Cache by hash of the extracted context; if Ollama is not available, Exodus works as before,
  with no inferences.
- ✅ First delivery: one responsibility sentence per system/container/component (shown in the
  draw.io boxes and in the inventory) + `overview.md`.
- **Changes for the user:** local Ollama with `qwen3.5:9b`; `enrichment-cache.json` and
  `overview.md` in `exodus-output/<project>/`.

## 7. ✅ Use cases (`use-cases.md`) (done on 2026-09-25)
**Depends on:** 4 and 6.
- ✅ One use case per entry point: trigger, steps, data and systems touched, each statement
  with file:line.
- ✅ The AI reads only the entry point's file and those of the classes it cites in the same
  system (up to 5 files / 12 thousand characters; no call graph yet).
- **Decisions (2026-09-25):** only the **5 main entry points per system**, a deterministic
  ranking in the domain (`core_entry_points`): containers take turns by centrality (the 1st
  entry of each, then the 2nd…); within a container, more relationships with evidence in the
  entry point's file or that cite it in the label, then HTTP/SOAP > consumer > job > command,
  then name. A step whose citation does not exist in the files sent is dropped; "touches" only
  accepts elements the container relates to. Use cases live in the graph (`SCHEMA_VERSION`
  1.4). Generic entries (`ICommandHandler<TCommand>` in decorators) no longer count as entry
  points.
- **Changes for the user:** `use-cases.md` and `use-cases-cache.json` in
  `exodus-output/<project>/`; an *Evidence* column in the inventory's entry points table.

## 8. ✅ Data: servers, databases, main tables and procedures (done on 2026-09-25)
**Why here:** it gives the size and coupling of the data for the migration decision, no AI.
- Only what is common to each **database type**, read from the code (no ORM nor frameworks):
  - relational: SQL in strings and `.sql` files — tables (`FROM`/`JOIN`/`INSERT INTO`/
    `UPDATE`/`DELETE FROM`/`CREATE TABLE`) and procedures (`EXEC`/`CALL`/`CREATE PROCEDURE`);
  - document (Mongo): `db.<collection>`, `getCollection("x")`, `GetCollection<T>("x")`,
    `collection("x")`.
- A section in `inventory.md`: server → database → up to 10 tables/collections and 10 procedures
  (by how many files cite them, "+N more"), who uses them; the full list only in `graph.json`.
- **Decisions (2026-09-25):** the call graph went to the backlog; no `reads`/`writes` (the arrow
  stays single, the diagram unpolluted); no new file; a table in a container with more than one
  database of the same type is "database not determined"; Pacco (collections only through
  Convey `AddMongoRepository`) gets no collection list — accepted (only Availability, which uses
  the driver directly, shows `resources`).
- **Changes for the user:** "Data stores" in `inventory.md` becomes a list per server with the
  main tables/collections and procedures; the full list (with file:line) in `graph.json`.

## 9. ✅ Migration recommendations (`migration.md`) (done on 2026-09-25)
**Depends on:** 5, 6, 7 and 8.
- 7R per container (current AWS strategies: Retire, Retain, Rehost, Relocate, Repurchase,
  Replatform, Refactor — [AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/migration-strategies.html)),
  with rationale and evidence, in **two paths**: fast (Rehost when the runtime does not run in a
  Linux container — .NET Framework/WCF/Web Forms/Remoting/MSMQ, coupled Java EE, unsupported
  Python —, otherwise Replatform) and modern (Refactor, or "= fast" if nothing needs to be
  rewritten). A **"Retire?"** warning for a container with no entry point nor incoming call.
  Retain, Repurchase and Relocate cannot be deduced from code: legend only.
- AWS mapping **by deterministic rules only** (a table per piece type, both paths; no rule →
  "No rule: evaluate"). No AI.
- Waves: **wave 0 = foundation** (platform and brokers); then groups tied by a shared database
  or mutual dependency; callees (HTTP/SOAP) go before callers; tie → fewer HIGH risks first.
  Asynchronous events do not change the order; a dedicated queue goes with its consumer.
  Computed over all the systems analyzed together.
- **Decisions (2026-09-25):** 7R instead of 6R; **no effort estimate** (no calibrated base);
  rules in the domain (`domain/migration.py`, pure, like the risks). Wave = topological level
  (within it, fewer HIGH risks first); the reason cites only the dependency that holds the group
  in the wave ("+N in earlier waves").
- **Fixes along the way:** `GrpcServiceHost` is no longer detected as WCF (a false risk in
  Pacco); gateway routes (Ntrada `upstream`, Ocelot `UpstreamPathTemplate`) become HTTP entry
  points (without this, gateways showed as Retire candidates).
- **Changes for the user:** new `migration.md`; gateways list their routes under "Entry points".

## 10. ✅ TO-BE + ADRs (done on 2026-09-25)
**Depends on:** 9.
- **Two L2 diagrams** (one page per system), in the AWS architecture style (`mxgraph.aws4`
  icons; AWS Cloud → Region → groups by category: Edge, Compute, Integration, Data, Security,
  Observability, Platform; no VPC/subnets, which the code does not show):
  - `to-be/replatform.drawio`: the deterministic targets of item 9; AS-IS links with the medium
    swapped;
  - `to-be/refactor.drawio`: architecture **proposed by the AI** (local Ollama), prioritizing
    **cost → security → performance**, choosing only from the catalog
    `exodus/catalog/refactor-catalog.json` (26 types, 86 options, NoSQL included). Links = the
    AS-IS ones transformed by the decisions (merge, database split, messaging swapped, platform
    removed); no made-up arrow.
- AI in two steps: structural per system (merges, shared database) + one call per piece. An
  invalid answer or Ollama down → the catalog's first option, with a note.
- ADRs: one per grouped decision, built from the answers (no extra call), in
  `to-be/adr/NNN-title.md`.
- **Slices:** ✅ 10a replatform; ✅ 10b AI + refactor; ✅ 10c ADRs (all on 2026-09-25).
  - 10a: groups by category = AWS color/legend over the AS-IS layout (the boundary's inner
    margin has no room for zone labels); external systems show as "Outside AWS";
    `render --to-be`; the default command generates AS-IS and TO-BE.
  - 10b: each piece's type comes from what is extracted (a container called over HTTP = API
    even with no detected route); the AI runs in `scan` (cache `refactor-cache.json`), decisions
    in `graph.json` (schema 1.5); the prompt carries only extracted facts, never source code.
    Pacco: 36 valid choices in ~3 min (no merges: no shared database nor wave group).
  - 10c: ADRs generated in `render --to-be` (those of a previous render are deleted first, so no
    decision that no longer exists is left behind); Pacco: 7 ADRs.
- **Changes for the user:** `to-be/replatform.drawio`, `to-be/refactor.drawio`, `to-be/adr/`,
  `refactor-cache.json`; the scan gets the "Preparing refactor proposal" step (~1 Ollama call
  per piece); `graph.json` schema 1.5.
- **Decisions (2026-09-25):** L2 only; AWS style with groups by category (no network); refactor
  by AI (not deterministic, but restricted to the catalog and justified); the AI runs in `scan`
  and the decisions live in `graph.json`; `render --to-be`.

## 11. ✅ HTML report (done on 2026-09-25)
- A single page with diagrams, inventory, risks, use cases and recommendations — to share with
  decision makers.
- **Decisions (2026-09-25):** a single self-contained `report.html` (offline, no server);
  diagrams in SVG drawn by Exodus from the same layout (TO-BE with the AWS category color and
  the service name, without the official icons, which only exist in draw.io; a link to the
  `.drawio` files); order: executive summary → AS-IS L2 (L1 if several systems) → HIGH risks →
  migration (paths and waves) → TO-BE (replatform, refactor and decisions) → collapsed details
  (inventory, use cases, L3, ADRs); fixed texts in Portuguese (the AI already writes in
  Portuguese; the `.md` files do not change); generated on every `render`. MCP removed.
- **Adjustments after seeing the result (screenshots in headless Chromium):** diagrams fitted to
  the width and zoomed with a click; equal high risks and migration paths grouped in one row;
  refactor decisions grouped by service (rationales collapsed); the containers' overview
  collapsed; the domain's fixed phrases translated in the report. The detail sections reuse the
  `.md` files and keep their English structure.
- **Changes for the user:** `report.html` in `exodus-output/<project>/` on every `render`.

## 12. ✅ Project documentation (`documentation.md`) (done on 2026-09-25)
**Why:** the team needs to understand the legacy system simply (what it is, what it is for, what
weighs on the migration), not only decide the migration.
- The structure of `docs/exodus.md`, based on the
  [Architecture Master Playbook](docs/architecture-master-playbook.md): sections 0–14, no
  diagrams, in Portuguese.
- Sections from the code (deterministic): overview, scope, what it does, constraints and
  dependencies, drivers (high risks grouped), decisions (7R, targets, refactor), how it works,
  deployment (grouped by image), tests, risks, waves, open questions (unresolved data sources,
  tables with no database, pieces with no rule, Retire candidates).
- Sections inferred by the AI (one call per system, cache `project-cache.json`): problem and
  goals, principles, assumptions and glossary. The facts go numbered; a principle with no valid
  cited fact is dropped; a glossary term must appear in the facts. Without Ollama: the
  playbook's guiding questions for the team to answer.
- **Decisions (2026-09-25):** the AI fills the business sections (marked *inferred*);
  `documentation.md` in Portuguese; schema 1.6 (project context in `graph.json`).
- **Validated:** Pacco (microservices, CQRS/events, layers, API gateway; domain glossary) and
  dotnet-billing (billing/invoicing, WCF/MSMQ).

## 13. ✅ RAG example: the legacy's written documentation (done on 2026-09-25)
**Why:** a project to learn RAG on a real case — the business sections of `documentation.md`
come only from the names in the code today; the legacy's READMEs and `docs/` say more (Pacco has
14 files, ~30 KB, which do not fit in the prompt together with the facts).
- Reading: `.md`, `.txt`, `.rst`, `.adoc`, `README*` (no new dependency), split into pieces by
  heading/paragraph (~800 characters) with file:line.
- Embeddings: `bge-m3` (MIT, multilingual) in the local Ollama. Vector database: **Qdrant**
  (Apache 2.0) in Docker via `docker-compose.yml`, called over HTTP (standard library),
  collection `exodus-<project>`, dashboard at `localhost:6333/dashboard`; reindexes only what
  changed.
- Use: fixed searches (problem, goals, terms, assumptions, architecture) → numbered pieces
  (D1…) together with the facts (F1…) in the project context call; citations "basis:
  `docs/x.md:12`".
- `rag-trace.md` per project: question → pieces (file:line, score, text) → answer.
- Without Qdrant (or without the model): a warning and Exodus goes on as today.
- **Decisions (2026-09-25):** use case = the legacy's documentation; Qdrant; `bge-m3`; text
  formats only; Qdrant started manually, optional; trace in `rag-trace.md`; pieces in the same
  step as the project context.
- **What the trace taught (validation on Pacco):** (1) each service's README repeats the same
  introduction and took the top 5 → deduplication by text in the search; (2) Markdown underlined
  headings (`Title` + `----`) were not recognized and glued different sections together →
  reader fixed; (3) Portuguese questions against English documents give low similarity
  (~0.46–0.51, cut at 0.45); (4) `.txt` files that are configuration dumps (e.g.
  `docker-images.txt`) come in as noise. Pacco: 89 pieces; incremental reindexing (64 new, 40
  removed after the reader fix); 4 document citations in `documentation.md`.
- **Changes for the user:** `docker-compose.yml` (Qdrant v1.19.1), `rag-trace.md`, the
  "Indexing legacy documentation (RAG)" step in the scan; `graph.json` schema 1.7.

## 14. ✅ Document language (done on 2026-09-25)
**Why:** the code and the repository go to an English-speaking audience; the generated documents
serve teams that read Portuguese or English.
- Code, identifiers, comments, README, `CLAUDE.md`, this roadmap and `docs/` in English.
- `--lang pt-br|en` (default `pt-br`, the previous behavior) in the default command, `scan` and
  `render`: fixed texts of `report.html`, `documentation.md` and `rag-trace.md`, and the language
  the AI is asked to answer in (descriptions, use cases, refactor rationales, project context).
- **Decisions (2026-09-25):** the domain writes no sentence in a language (open questions are
  structured, `OpenQuestion`); fixed texts side by side in the renderers (`pick(language, pt_br,
  en)`); the prompts in `pt-br` stay byte-identical, so the existing caches keep working (the
  cache key is the prompt: each language has its own answers); the RAG search questions
  follow `--lang` too (same questions as before in `pt-br`); SVG labels of the report in English, like the
  draw.io files; inventory, risks, migration, ADRs and diagrams stay in English.
- **Changes for the user:** nothing without the flag. With `--lang en`, the AI writes its texts
  again on the first run (a few minutes). Use the same `--lang` in `scan` and `render`.

---

## Backlog (no order; comes in when needed)
- Layout: containers with no relationship stack in a single column; group the loose ones in a
  grid (inherited from item 2).
- Word/PDF in the RAG base (text formats only today; it would need `python-docx`/`pypdf`).
- The `.md` files that are always in English (inventory, risks, migration, ADRs) following
  `--lang`, if the audience asks.
- A method-level call graph (tree-sitter) → deterministic use case steps (left item 8 by the
  big-picture rule).
