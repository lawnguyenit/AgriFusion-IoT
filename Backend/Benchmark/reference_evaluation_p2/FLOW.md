# Implemented P2 responsibility flow

runner locks pilot scope → evidence verifies current graph/READY/P1 and source
snapshot → source adapter loads project cache and canonical segments → cache
reproduces existing full-control forecasts → mask_roles constructs A/B/C/D
public EvaluationSegment inputs → primary_bounds consumes public inputs only →
validation joins audit reference downstream → persistence writes new P2 evidence.

For D: original pair CSV endpoints → witness traceback from original public inputs
→ independent labels/Brier validator → full completion NPZ → reopen and validate
saved bytes against original forecasts and segment/key/score/observation contracts.

The R0 traceback stores predecessor state/bit per time step; segments reset state
and are independently optimized because the global error allowance is exactly0.
R>0 is explicitly rejected. The original rolling frontier remains unchanged.

mask_roles keeps feature and reference SHA256 seed namespaces separate. A uses
the original unmasked forecast cache; B creates one frozen masked forecast per
case; C varies reference11/22 around that exact B prediction; D is historical v1.
The full truth is retained only by source simulation and downstream audit owners.
No new feature/schema is introduced into the existing evaluator contract.

Only the new output tree is written. Original artifact hashes are rechecked
before final tables, validation, summary and P2_READY are written. Missing/changed
cache, snapshot, graph or input fails loudly. Existing output paths are refused.
Source code copied into output plus provenance tie pilot bytes to locked v1.
No fit, tuning, threshold reconstruction, split migration or original READY update.
