# CONSTRUCTION.md

Production and construction policy for **Looming Dark I: Island**.

## Production principle

Build systems and reusable tools before repetitive manual content where doing so will materially reduce future labor, token use, or error rate.

## Repository authority

The repository stores approved design, task state, asset provenance, implementation state, and automation configuration. If chat history and repository state disagree, repository state wins unless the discrepancy is explicitly resolved.

## Work lifecycle

Preferred lifecycle:

`discuss -> decide -> record -> create task -> route worker -> execute -> validate -> review -> merge -> update project state`

Avoid copy/paste relays between ChatGPT, Codex, Cursor, and specialist tools when an API, CLI, MCP server, webhook, or repository-backed task packet can replace them.

## Scene and file ownership

Unity scene and prefab files are high-conflict assets. Parallel workers must use explicit ownership.

Write-lock classes include, unless a task explicitly coordinates them:

- `*.unity`
- `*.prefab`
- `Packages/manifest.json`
- `Packages/packages-lock.json`
- `ProjectSettings/*`
- shared input-action assets
- global bootstrap/game-state managers

## Asset Registry

No third-party or generated production asset should be considered cleared for shipping until registered.

Minimum registry fields:

- `asset_id`
- `name`
- `category`
- `source_type` (`purchased`, `free`, `generated`, `internal`, `commissioned`)
- `source_name`
- `source_url_or_reference`
- `vendor_or_creator`
- `license`
- `commercial_use_status`
- `acquired_or_generated_at`
- `ai_tool`
- `ai_model`
- `generation_job_id`
- `input_reference_ids`
- `modifications`
- `unity_path`
- `no_external`
- `notes`

`NO_EXTERNAL: true` means the asset/reference may not be uploaded to third-party AI or external services.

## Generated asset pipeline

Preferred flow:

`approved reference/spec -> generation job -> raw output quarantine -> provenance registration -> technical QA -> cleanup/retopo/UV as needed -> Unity import -> visual QA -> production approval`

Do not bypass the raw/quarantine stage for generated production assets.

## Naming

Use predictable, searchable names. Preferred production prefix: `LDI_`.

Examples:

- `LDI_Harbor_HarborMaster_EXT_A`
- `LDI_Harbor_WeatherStation_INT_A`
- `LDI_Beach_Bonfire_POI_A`
- `LDI_SYS_HarborStormTimer`

Avoid names such as `Cube (17)`, `New Prefab`, `final_final`, or unexplained abbreviations in production folders.

## Blockout policy

The full Island should exist at macro-blockout level before detailed world production so the following remain coherent:

- coastline and coves;
- elevation and cliffs;
- Harbor;
- Lighthouse;
- Town;
- Old Town;
- Manor;
- Crypt relationship;
- river/water crossings;
- roads and trails;
- vehicle routes;
- walking routes;
- blocked routes and shortcuts;
- major sightlines.

Detailed production remains focused first on Beach -> Harbor -> Lighthouse -> forest-road transition.

## Reusable tooling preference

Before asking an agent to repeat a manual operation many times, consider creating a reusable Editor/tooling abstraction such as:

- blockout building generator;
- landmark marker;
- road/path generator;
- encounter volume;
- timer/state volume;
- visibility/sightline marker;
- character-route overlay;
- asset import validator;
- provenance registrar.

The objective is to spend high reasoning once to create a reliable tool, then let lower-cost workers operate it repeatedly.

## Paid-service rule

Specialist subscriptions should be activated when there is a prepared backlog large enough to justify the billing period. Prefer testing free tiers/API sandboxes before paid activation.

Do not burn paid credits for unconstrained experimentation when equivalent structural testing can be performed with placeholders.
