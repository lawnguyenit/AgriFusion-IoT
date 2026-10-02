# Paper submission provenance and reproducibility package

## Task Objective

Prepare the frozen WADE/AgriFusion paper repository for submission: verify official Stuard Version 2 raw data, record source provenance, and provide an exact way to regenerate the frozen V6 manuscript tables from the V8 paper artifacts. Do not train models, change experiments, or alter scientific claims.

## User Intent

The user says the scientific core is frozen and wants submission packaging. The requested order is Stuard checksum verification, a paper GitHub version, a reproducibility package that identifies source/config/split/model/prediction/bootstrap/environment artifacts and table commands, then Zenodo DOI and administrative submission details. The attached PDF is manuscript context; its editorial checklist is evidence, not an independent authorization to alter scientific scope. The user explicitly authorized repository and Git work associated with preparing the paper version.

## Current Behavior

- The V8 manuscript states the experimental core is frozen at V6 and retains submission TODOs for Stuard source verification, artifact archiving, authorship/admin details, journal formatting, and final table/figure exports.
- The external intake lane previously recorded Stuard Mendeley metadata while downloading raw streams from a GitHub mirror. Each existing raw release manifest records SHA-256 and original origin.
- The frozen research framework and exact artifact locations are documented in Docs/research/WADE_RESEARCH_FRAMEWORK_FROZEN.md. Generated model and bootstrap artifacts are under ignored Backend/Output_data paths.
- The existing three-dataset ZIP contains 202 files indexed by package_manifest.json; 23,862,096 bytes compressed and 74,821,193 bytes uncompressed.
- Current main was 1cac56f before this task. The user has an unrelated working change in IoT_Node/lib/Config/src/Config.h and untracked tmp/. Preserve and exclude both from the paper release.

## Confirmed Facts

- Official Mendeley dataset 35wh56287y, Version 2, DOI 10.17632/35wh56287y.2, publishes three pipeline input CSVs plus indicators.csv and README.TXT.
- The three CSVs were individually downloaded using official Version 2 file URLs. Official API hash, downloaded-file hash, and the current raw Stuard hashes match exactly:
  - environmental: 1,206,822 bytes; SHA-256 282c2e5366510416e7e9de8c1750cb67d6c773ce0d985aae54206f50a7743ead
  - soil: 3,500,782 bytes; SHA-256 b6ec194a052863a17c57ad2303e93afe12ea101ffd8773865903e95f2186f9dc
  - water meter: 3,038,311 bytes; SHA-256 aa128bd3d3fc9ca971326870555c9eadd8f76c054611a87b90bc7c45e591057c
- Local snapshot compared: release stuard_source_20260929. Its raw_manifest.json SHA-256 is 3cdcd205f8a51282f0714c60f507ebc85e5c0ff54296cce151b1daed1d1074dd.
- A first attempt to fetch Mendeley's archive ZIP from its S3 URL returned AccessDenied. The official direct links for all three relevant input files succeeded and matched official metadata. The complete archive ZIP hash was not checked.
- The frozen result archive contains the exact RQ1 primary run, Stuard/UCI primary model runs, and final nested Stuard controls. It includes configs/manifests, feature contracts, split assignments, predictions, per-anchor losses, support audits, models, and bootstrap outputs.
- The new paper table command verifies all 202 package files and regenerates Tables 2–4. All displayed values match the V8 manuscript.
- The result ZIP SHA-256 is 499bb2fd9ed485073b8d27c40fdc0e01ed825b47db4766afffce7fe7f3d07479.

## Unresolved Questions

- Which journal and its reference, figure, and word limits will govern final manuscript styling?
- Final authorship order, corresponding author, CRediT, funding, conflicts, acknowledgements, and journal-specific AI disclosure remain user-provided details.
- Zenodo DOI and final Data/Code Availability statement depend on the GitHub release and Zenodo archive being minted.

## Assumptions

- V6 names the frozen experimental core in the manuscript; V8 names the current manuscript draft.
- No experiment, threshold, split, seed, model, or bootstrap will be rerun or modified.
- Raw datasets remain linked at official repositories; the GitHub asset holds derived/processed research artifacts and source hashes.
- User-local changes and untracked scratch files are not part of the paper release.

## Affected Modules and Files

- Backend/Benchmark/external_intake/sources.py: official Stuard Version 2 file URLs and official dataset title/citation.
- Backend/Benchmark/external_intake/README.md and FLOW.md: document the current official download behavior and verification.
- Backend/Benchmark/model_suite/reporting/paper_tables.py and paper_tables_main.py: derive Tables 2–4, verify the result bundle inventory, and write CSV/Markdown outputs.
- Docs/research/reproducibility/paper-v1.0/: source verification manifest, table environment, and reproducibility guide.
- README.md: entry link for paper reproduction.
- Docs/worklogs/2026-10-02-paper-submission-provenance-package.md: this worklog.
- Ignored raw/result artifacts were inspected but not modified.

## Implementation Plan

1. Inspect the frozen design, source manifests, output package, and all callers without executing a fit.
2. Record official Stuard Version 2 hashes and byte comparisons; update future Stuard downloads to use Mendeley URLs.
3. Add a paper reproduction guide and CLI to rebuild Tables 2–4 from the frozen ZIP after integrity checks.
4. Prepare the release scope while excluding user-local files; defer DOI creation until after GitHub release.
5. Validate source/manifest consistency, rebuild the paper tables from persisted results, and inspect the scoped diff/status.

## Architectural Decisions

- Keep research provenance in Docs/research/reproducibility, separate from production telemetry Core and generated outputs.
- Let reproduction docs reference authoritative Benchmark manifests and run outputs rather than duplicate training logic or move generated artifacts.
- Keep table transformations as reporting functions and source ZIP loading/integrity/output orchestration in a small CLI module. Table generation consumes saved outputs and performs no fitting or resampling.
- Commit small verification metadata and the table builder; attach the existing 24 MB result archive to the GitHub release and keep raw source downloads at their official repositories.
- The PDF's remaining TODOs are retained as submission check items; no TODO text was deleted from the manuscript.

## Progress Status

Repository package and official Stuard verification are complete. Table regeneration is complete and matches the V8 paper. Remaining work is the paper-only Git commit, tag and GitHub release asset; Zenodo and journal-specific administration follow afterward.

## Validation Commands and Results

- Read the root and Benchmark AGENTS/READMEs, intake adapter and FLOW, frozen WADE framework, current project-state/worklogs, and V8 manuscript.
- Queried the Mendeley Version 2 public metadata/files API. Downloaded all three required official CSV files to OS temporary storage.
- Compared official API SHA-256, downloaded official SHA-256, local raw SHA-256 and byte size; all three inputs match.
- Ran: python -m Backend.Benchmark.model_suite.reporting.paper_tables_main --bundle Backend/Output_data/three_dataset_web_analysis_20261001/three_dataset_web_analysis_20261001.zip --output-dir <OS-temp>. Passed verification of the 202-file manifest and regenerated Tables 2–4. Table 2 values (including pooled log-loss and fold-mean macro-F1), Table 3 values, and Table 4 nested contrasts match the V8 displayed values.
- The table rebuild read serialized model outputs; no model fitting, experiment, bootstrap resampling, or test suite was run.

## Compatibility Impact

No canonical schema or model API changed. New Stuard --download calls now fetch the official Mendeley Version 2 files. Existing historical raw snapshots/manifests are unchanged. Source metadata title/citation now matches the current official Version 2 record. The table CLI and provenance package are additive.

## Remaining Risks and Follow-up Work

- The full Mendeley archive ZIP endpoint was inaccessible; individual raw inputs were downloaded and byte-verified through official Mendeley file URLs.
- GitHub tag/release has not yet been created. Its commit must exclude IoT_Node/lib/Config/src/Config.h and tmp/. Attach the verified result ZIP with its recorded SHA-256.
- Journal-specific styling, final figure exports, DOI creation, availability statements, and author declarations remain downstream actions.
