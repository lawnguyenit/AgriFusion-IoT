"""CLI orchestration; stages retain independent failures for later resumption."""
from pathlib import Path
import json
import traceback
from .config import cells
from .contracts import FailedSupport
from .reporting import write_report, export_sync_tree
from .sensitivity import sensitivity_case
from .smoke import smoke_local
from .solver_stage import solve_case
from .stages import audit_source, load_prepared, fit_source, evaluate_case
from .storage import atomic_json
from .validation import validate_local


class Pipeline:
    def __init__(self, store, datasets=None):
        self.store = store
        self.sources = [s for s in store.config["sources"] if not datasets or s["dataset_id"] in datasets]
        if not self.sources:
            raise ValueError("No requested source is present in the config")
        self.errors = []; self.prepared_cache = {}

    def attempt(self, stage, key, action):
        # Stage contexts preserve traceback/partial outputs. The top-level loop
        # accounts for failures, continues independent sources and returns nonzero.
        try:
            return action()
        except Exception as error:
            record = {"stage": stage, "key": key, "error_type": type(error).__name__,
                      "message": str(error), "invocation_id": self.store.invocation_id}
            self.errors.append(record)
            if stage == 'audit':
                self.store.invalidate('audit',key)
            atomic_json(self.store.root / "BLOCKERS.json", self.errors)
            (self.store.root/'STUDY_STATUS.md').write_text(
                f"# Checkpoint needs attention\n\nLast failure: {stage} {key}: {type(error).__name__}: {error}.\n"
                "See BLOCKERS.json, RUN_INDEX.csv and ACTIVE_GRAPH.json. No full-plan completion is asserted.\n",encoding='utf-8')
            print(f"FAILED {stage} {key}: {type(error).__name__}: {error}", flush=True)
            traceback.print_exc()
            return None

    def _stage_lookup(self, stage):
        return {json.loads((p/'run_manifest.json').read_text())["unit_key"]: p for p in self.store.active_units(stage)}

    def _prepared(self, path):
        if path not in self.prepared_cache:
            self.prepared_cache[path] = load_prepared(path)
        return self.prepared_cache[path]

    def _fit_gates(self):
        validated = any(json.loads((p/'metrics.json').read_text()).get('full_P2_gate',False)
                        for p in self.store.active_units('validate'))
        if not validated or not self.store.active_units('smoke'):
            raise FileNotFoundError('Real-source fit requires full validate (with legacy fixture) and local smoke first')

    @staticmethod
    def _missing(message):
        raise FileNotFoundError(message)

    def audit(self, download=False):
        for source in self.sources:
            self.attempt("audit", source["dataset_id"], lambda s=source: audit_source(self.store, s, download))

    def validate(self, fixture_dir=None, unit_only=False):
        if fixture_dir is None:
            fixture_dir = self.store.config.get("runtime", {}).get("reference_fixture_dir")
        return validate_local(self.store, fixture_dir, unit_only)

    def smoke(self):
        audits = self._stage_lookup("audit")
        selected = [(s["dataset_id"], audits[s["dataset_id"]]) for s in self.sources if s["dataset_id"] in audits]
        return smoke_local(self.store, [p for _, p in selected],
                           [(sid, self._prepared(p)[0]) for sid, p in selected])

    def fit(self):
        self._fit_gates()
        audits = self._stage_lookup("audit")
        for source in self.sources:
            sid = source["dataset_id"]
            if sid not in audits:
                self.attempt("fit", sid, lambda: self._missing("Run a current audit first"))
                continue
            path = audits[sid]; segments, metadata = self._prepared(path)
            for seed in self.store.config["training"]["training_mask_seeds"]:
                self.attempt("fit", f"{sid}__{seed}",
                             lambda seed=seed: fit_source(self.store, sid, seed, path, segments, metadata))

    def evaluate(self):
        audits = self._stage_lookup("audit"); fits = self._stage_lookup("fit")
        for source in self.sources:
            sid = source["dataset_id"]
            if sid not in audits:
                self.attempt("evaluate", sid, lambda: self._missing("Run a current audit first"))
                continue
            audit_path = audits[sid]; segments, metadata = self._prepared(audit_path)
            for seed in self.store.config["training"]["training_mask_seeds"]:
                fit_path = fits.get(f"{sid}__{seed}")
                if fit_path is None:
                    self.attempt("evaluate", f"{sid}__{seed}", lambda: self._missing("Required current fit is unavailable"))
                    continue  # Missing fit remains in plan/accounting, not a fabricated model.
                for policy, mask_seed in cells(self.store.config):
                    key = f"{sid}__{seed}__{policy}__{mask_seed}"
                    self.attempt("evaluate", key, lambda seed=seed, policy=policy, mask_seed=mask_seed:
                                 evaluate_case(self.store, sid, seed, policy, mask_seed, audit_path,
                                               fit_path, segments, metadata))

    def sensitivity(self):
        allowed = {s["dataset_id"] for s in self.sources}
        if not self.store.active_units("evaluate"):
            raise FileNotFoundError('Run current evaluation cases before sensitivity')
        for path in self.store.active_units("evaluate"):
            identity = json.loads((path/'case_identity.json').read_text())
            if identity["dataset_id"] in allowed:
                self.attempt("sensitivity", path.name, lambda p=path: sensitivity_case(self.store, p))

    def solver(self):
        allowed = {s["dataset_id"] for s in self.sources}
        if not self.store.active_units("evaluate"):
            raise FileNotFoundError('Run current evaluation cases before generic solver')
        for path in self.store.active_units("evaluate"):
            identity = json.loads((path/'case_identity.json').read_text())
            if identity["dataset_id"] in allowed:
                self.attempt("solver", path.name, lambda p=path: solve_case(self.store, p))

    def report(self):
        return write_report(self.store)

    def export(self, without_audit_truth=False):
        if not self.store.active_units('report'):
            raise FileNotFoundError('Run report for the current validated graph before export')
        return export_sync_tree(self.store, without_audit_truth)

    def all(self, fixture_dir=None):
        self.audit(download=False)
        self.validate(fixture_dir=fixture_dir, unit_only=False)
        self.smoke()
        self.fit(); self.evaluate(); self.sensitivity(); self.solver()
        self.report()
        return self.export()
