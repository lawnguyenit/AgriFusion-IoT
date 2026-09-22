# Repository hygiene

## Tracked public surface

The clean-clone orientation is provided by the root README, `public-docs/`,
module READMEs/FLOW files, source code, tests and selected architecture
assets.

## Local or generated material

The following must remain local or be handled as explicit release artifacts:

- `Backend/Output_data/` — generated Layer0/Layer1 outputs;
- benchmark `artifacts/`, datasets, reports and model files;
- `IoT_Node/.pio/` — PlatformIO build state;
- `Frontend/tmp-edge-profile/` — browser profile state;
- `Secrets/`, `Backend/.env`, frontend local Firebase config and
  `IoT_Node/lib/Config/src/Config.private.h` — credentials or local secrets;
- large research datasets and dated local evidence under `Docs/`.

Do not add a generated output to the source tree merely to make a README
example appear to work. Use a small fixture or a documented local input
instead.

## Status vocabulary

Use these distinctions in documentation and reports:

- **implemented** — source exists;
- **verified** — a reproducible check or runtime evidence exists;
- **experimental** — a controlled probe or hardware path, not a production
  guarantee;
- **legacy/compatibility** — retained for consumers but not the canonical
  owner;
- **not verified** — the repository cannot prove the claim yet.

## Safe contribution sequence

1. Read the nearest `AGENTS.md` and the relevant README/FLOW file.
2. Inspect the current working tree before changing files.
3. Keep raw data immutable and write derived artifacts to a new output path.
4. Run focused tests and a broader regression check when a shared contract
   changes.
5. Record exact validation commands and unresolved gaps in the task worklog.
