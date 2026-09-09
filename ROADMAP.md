# Looming Dark I — Automation-to-Harbor Roadmap

Target window: September 9, 2026 -> October 31, 2026.

## Phase 0 — Shared brain and control contracts
**Sep 9–12**

- Repository initialized.
- Shared `AGENTS.md` established.
- `CONSTRUCTION.md` established.
- Machine-readable task packet schema established.
- Asset provenance schema established.
- Control-plane architecture documented.
- Connect Cursor and Codex to this exact repository.
- Establish local development/worktree conventions.

**Exit test:** ChatGPT, Codex, and Cursor can all read the same rules/specs from `mjhanratty/loomingdark_island`.

## Phase 1 — Worker automation proof
**Sep 12–17**

- Add Cursor worker adapter/CLI test.
- Add Codex worker adapter/test where available.
- Establish task status transitions (`draft`, `approved`, `running`, `review`, `complete`, `failed`).
- Establish structured completion report.
- Establish quota/run-class state file.
- Connect Unity 6 project.
- Connect/validate Unity MCP.

**Exit test:** one harmless structured task routes to a worker, executes, validates, and records completion without prompt copy/paste.

## Phase 2 — Specialist-tool free tests
**Sep 15–20, overlapping Phase 1**

- Meshy free/API capability test.
- Tripo free/API capability test.
- Test generation-job tracking and provenance capture.
- Test automatic placement of raw outputs into controlled storage.
- Do not activate paid plans until a production backlog justifies them.

**Exit test:** one test asset request can be created, executed on an available free route, tracked, and registered.

## Phase 3 — Full Island macro blockout
**Sep 18–25**

Establish the physical truth of the Island:

- coastline, coves, cliffs, beaches;
- forest and elevation masses;
- Harbor;
- Lighthouse;
- Town;
- Old Town;
- Manor;
- Crypt relationship;
- river/water crossings;
- major roads/trails;
- vehicle and walking routes;
- blocked routes/shortcuts;
- major sightlines.

**Exit test:** Lighthouse panorama and Manor visibility work at blockout scale.

## Phase 4 — Beach detailed blockout
**Sep 25–Oct 3**

- wake-up beach area;
- seawall/forest containment;
- movement/tutorial route;
- bonfire/Harbor visual pull;
- Beach-to-Harbor transition;
- traversal timing and scale.

## Phase 5 — Harbor detailed blockout
**Oct 1–17**

Represent and route:

- Harbor Master;
- Boat Repair;
- Boat Storage;
- Fish House;
- Supply Shop + apartment;
- Weather Station;
- piers/docks;
- seawalls;
- vehicle areas;
- primary/secondary paths;
- selected interiors.

Build reusable blockout/editor tools where repetition justifies them.

## Phase 6 — Harbor systems skeleton
**Oct 10–24**

- interaction framework;
- pickups/inventory skeleton;
- door/access framework;
- character ability hooks;
- Weather Station timer activation;
- storm/fog state hooks;
- checkpoint/save skeleton;
- basic apparition event;
- vehicle placeholder behavior.

## Phase 7 — Beach -> Harbor playable integration
**Oct 21–31**

- continuous playable route;
- blockout QA;
- traversal and scale corrections;
- early lighting/fog/weather tests where useful;
- performance baseline on current development Mac;
- automation pipeline used for real production tasks.

## October 31 success definition

- Whole Island exists at coherent macro-blockout level.
- Beach and Harbor are materially detailed and connected.
- Lighthouse position/sightlines are validated.
- Key Harbor buildings/routes/interiors are represented.
- Core interaction/timer/state skeletons exist.
- ChatGPT, Codex, Cursor, Unity, and specialist-tool adapters are operating against shared repository state with minimal manual prompt relays.
