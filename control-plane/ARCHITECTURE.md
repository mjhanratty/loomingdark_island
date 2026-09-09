# Looming Dark Control Plane — Architecture

## Goal

Replace repetitive copy/paste coordination with a repository-backed workflow:

`discuss -> determine -> record -> route -> execute -> validate -> review -> report`

## Authority model

- Human approval remains authoritative for creative and spending decisions.
- Repository state is authoritative for project/task state.
- Workers operate from structured task packets.
- Unity is authoritative for actual game/editor state.
- Independent review is separated from implementation when model diversity materially reduces risk.

## Core worker roles

### ChatGPT — design and orchestration

- discuss goals and tradeoffs with the user;
- turn approved decisions into durable specs/tasks;
- maintain the shared repository state;
- coordinate control-plane evolution;
- avoid becoming a manual relay between workers.

### Codex — architecture and hard implementation

- difficult architecture;
- cross-system implementation;
- difficult debugging;
- integration work after design is approved;
- critical blocker resolution.

### Cursor — volume implementation

- bulk/repetitive implementation;
- editor tooling;
- safe refactors;
- parallel/background work;
- low/medium-cost execution where premium reasoning is unnecessary.

### Claude — independent review and escalation

Claude is a first-class worker because Claude Pro is already available to the project.
Its default lane is not duplicate implementation. It provides an independent model-family perspective for:

- architecture review;
- large-context consistency audits;
- acceptance-criteria review;
- diagnosis after repeated failed attempts;
- contradiction/coupling detection across systems;
- alternative reasoning when Codex or Cursor stalls.

Default policy: Claude reviews first and does not edit files owned by another active worker. If a task is explicitly escalated to Claude as implementation owner, normal ownership rules apply. Sonnet is the normal Claude lane; Opus is reserved for critical stubborn blockers when justified by the task/run policy.

## Initial components

1. **Repository state**
   - design specifications
   - task packets
   - asset registry
   - usage/cost state
   - worker/reviewer reports

2. **Router**
   - classifies tasks by type and run class;
   - selects Codex, Cursor, Claude, or specialist service;
   - considers quota/budget state;
   - decides when independent review is required;
   - prevents conflicting file ownership.

3. **Worker adapters**
   - Codex adapter
   - Cursor/Agent CLI adapter
   - Claude adapter
   - Unity MCP adapter
   - Meshy adapter
   - Tripo adapter
   - later specialist adapters as justified

4. **Validation**
   - repository diff/status
   - compile/test output
   - Unity console/project inspection
   - asset technical checks
   - acceptance-criteria result

5. **Independent review**
   - architecture-risk review where required
   - compare implementation against approved task/spec
   - report contradictions and unresolved risk
   - return implementation to the original owner unless escalation changes ownership

6. **Reporting**
   - task status written back to repository
   - changed files
   - checks performed
   - warnings/failures
   - review findings when applicable
   - cost/credit consumption when available

## Routing philosophy

Use the least expensive capable route and use model diversity deliberately rather than redundantly.

Examples:

- repetitive safe repository work -> low-cost Cursor/agent worker;
- ordinary Unity/C# implementation -> medium Cursor worker;
- difficult cross-system architecture -> high-reasoning Codex worker;
- major architecture change -> Codex implementation plus Claude independent review;
- repeated reasoning failure -> Claude diagnostic pass before another implementation attempt;
- image/reference to 3D -> primary asset generator, fallback only on failure;
- Unity scene/editor manipulation -> worker + Unity MCP;
- conflicting ownership -> queue, do not race.

## Planned MCP surface

A future `looming-dark-mcp` service should expose operations conceptually equivalent to:

- `get_project_status`
- `get_design_spec`
- `create_task`
- `get_task`
- `list_tasks`
- `assign_task`
- `request_review`
- `record_review`
- `record_decision`
- `register_asset`
- `create_asset_request`
- `get_asset_status`
- `get_usage`
- `recommend_worker`
- `get_unity_status`

The API names may evolve during implementation; the behavior and source-of-truth model should remain stable.

## Milestone 0 — free-stack proof

Before paid service activation, prove one end-to-end task can:

1. originate from a structured task packet;
2. route to Cursor or Codex;
3. modify an isolated test file/project object;
4. validate the change;
5. optionally route to Claude for independent review;
6. write a completion/review report;
7. preserve provenance/task state without manual prompt relays.

Then prove equivalent test calls against any available free Meshy/Tripo/API allowance before subscribing.

## October production objective

Infrastructure exists to support, not replace, production. By end of October the target is a coherent Beach and Harbor blockout/playable connection while the full Island exists at macro scale and the automation layer has been proven through real production tasks.
