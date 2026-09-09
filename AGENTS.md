# AGENTS.md

Shared operating rules for ChatGPT, Codex, Cursor, and any future agent working in this repository.

## 1. Source of truth

This repository is authoritative. Chat transcripts, local scratch notes, and model memory are not authoritative unless the relevant decision is written back here.

## 2. Engine and target

- Production engine: **Unity 6**.
- Use modern Unity tooling and hardware assumptions.
- “PS3-era” refers to **visual fidelity only**, not PS3 hardware/API limitations.
- Preserve PS1/PS2 survival-horror design language, pacing, atmosphere, and environmental storytelling.
- Modern lighting, fog, weather, audio, VFX, and post-processing are encouraged.

## 3. Immediate production priority

1. Establish shared automation/control infrastructure.
2. Block out the entire Island at macro scale.
3. Validate Lighthouse sightlines and Island readability.
4. Take Beach -> Harbor -> Lighthouse -> forest transition to vertical-slice fidelity first.
5. Do not prematurely art-finish Town, Old Town, Manor, or Crypt.

## 4. Work ownership

- Every implementation task should have a task packet.
- Every task packet must identify an owner/worker.
- Do not allow Codex and Cursor to modify the same Unity scene, prefab, package manifest, project setting, or global manager simultaneously.
- Use branches/worktrees for parallel work where practical.
- If file ownership is ambiguous, stop and resolve ownership before editing.

## 5. Scope discipline

- Do not redesign approved gameplay to make implementation easier without an explicit design decision.
- Do not modify unrelated files.
- Do not install or remove packages without explicit authorization in the task.
- Do not silently delete or replace assets.
- Do not convert a temporary workaround into permanent architecture without documenting it.

## 6. Validation

For code or Unity changes:

- compile after meaningful changes;
- inspect Unity console output when Unity is available;
- run relevant tests/checks;
- report new warnings/errors;
- verify acceptance criteria before marking complete.

A task is not complete merely because files were changed.

## 7. Asset provenance

Every external or AI-generated production asset must have provenance recorded in the asset registry.

Record at minimum:

- asset ID;
- source/tool/package;
- creator/vendor where applicable;
- license/status;
- acquisition or generation date;
- original source/reference;
- AI model/tool and generation job ID when applicable;
- modifications;
- final Unity path;
- restrictions such as `NO_EXTERNAL`.

Purchased assets are building blocks, not finished Looming Dark locations.

## 8. AI generation rules

- Do not spend paid generation credits without an approved asset brief unless the task explicitly allows exploration.
- Prefer one primary generator per asset request.
- Use fallback generators only after the primary route fails acceptance criteria.
- Reuse approved references, style guides, dimensions, topology targets, and material requirements.
- Generated outputs must enter the controlled asset pipeline before Unity production use.

## 9. Token / model economy

Use the least expensive model/run class that can reliably complete the task.

Suggested classes:

- `LOW`: inventory, search, docs, boilerplate, repetitive safe edits.
- `MEDIUM`: normal implementation, editor tooling, isolated refactors.
- `HIGH`: architecture, cross-system integration, difficult debugging.
- `CRITICAL`: severe blockers or failures spanning multiple systems.

Do not use high-end reasoning for mechanical work that a lower-cost worker can perform.

## 10. Completion report

Every worker should return or record:

- task ID;
- status;
- files changed;
- checks/tests performed;
- warnings/errors;
- unresolved items;
- follow-up tasks created or recommended.

## 11. Stop conditions

Stop and escalate instead of guessing when:

- a task conflicts with approved design;
- required input/reference is missing;
- a license/provenance question blocks safe use;
- another worker owns the same critical file;
- Unity/project state contradicts the task packet;
- continuing would spend paid credits outside the authorized scope.
