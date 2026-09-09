# Looming Dark Control Plane — Architecture

## Goal

Replace repetitive copy/paste coordination with a repository-backed workflow:

`discuss -> determine -> record -> route -> execute -> validate -> report`

## Authority model

- Human approval remains authoritative for creative and spending decisions.
- Repository state is authoritative for project/task state.
- Workers operate from structured task packets.
- Unity is authoritative for actual game/editor state.

## Initial components

1. **Repository state**
   - design specifications
   - task packets
   - asset registry
   - usage/cost state
   - worker reports

2. **Router**
   - classifies tasks by type and run class;
   - selects Codex, Cursor, or specialist service;
   - considers quota/budget state;
   - prevents conflicting file ownership.

3. **Worker adapters**
   - Codex adapter
   - Cursor/Agent CLI adapter
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

5. **Reporting**
   - task status written back to repository
   - changed files
   - checks performed
   - warnings/failures
   - cost/credit consumption when available

## Routing philosophy

Use the least expensive capable route.

Examples:

- repetitive safe repository work -> low-cost Cursor/agent worker;
- ordinary Unity/C# implementation -> medium worker;
- difficult cross-system architecture -> high-reasoning Codex worker;
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
5. write a completion report;
6. preserve provenance/task state without manual prompt relays.

Then prove equivalent test calls against any available free Meshy/Tripo/API allowance before subscribing.

## October production objective

Infrastructure exists to support, not replace, production. By end of October the target is a coherent Beach and Harbor blockout/playable connection while the full Island exists at macro scale and the automation layer has been proven through real production tasks.
