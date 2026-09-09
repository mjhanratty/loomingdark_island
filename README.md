# Looming Dark I: Island

Canonical repository for **Looming Dark I: Island**.

This repository is the shared source of truth for ChatGPT, Codex, Cursor, Unity, and the Looming Dark control-plane tooling.

## Current production target

Build a playable **Beach -> Harbor -> Lighthouse -> forest-road transition** vertical slice, while first establishing the macro blockout of the full Island so geography, sightlines, roads, character routes, and later level production remain physically coherent.

## Immediate milestones

1. Shared agent/project rules
2. Control-plane and task schema
3. Unity 6 project + MCP validation
4. Full Island macro blockout
5. Lighthouse sightline validation
6. Beach detailed blockout
7. Harbor detailed blockout
8. Beach-to-Harbor playable connection

## Source-of-truth rule

Project decisions, specifications, task packets, asset provenance, and implementation state must be written back to this repository. Chat histories are not authoritative project storage.

## Repository areas

- `design/` — approved game/world specifications
- `tasks/` — machine-readable work packets and lifecycle state
- `assets/registry/` — asset provenance and licensing metadata
- `control-plane/` — orchestration code and service adapters
- `scripts/` — local automation utilities
- `logs/` — generated run reports where appropriate
- `metrics/` — usage/cost snapshots where appropriate
- `game/` — Unity project when migrated/created

## Project constraints

- Engine: Unity 6
- Visual target: PS3-era geometry/material fidelity with modern Unity lighting, fog, weather, audio, VFX, and post-processing
- Design language: PS1/PS2 survival-horror pacing and atmosphere
- Initial production focus: Beach and Harbor, with Lighthouse and forest transition as the first vertical-slice boundary
- Specialist AI subscriptions should be activated only when an approved production backlog justifies them
