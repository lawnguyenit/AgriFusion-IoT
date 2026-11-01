"""Immutable, signature-addressed units and readable indexes for local runs."""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
import uuid


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), default=_json_default)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False,
                              default=_json_default) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def atomic_csv(path, rows, fieldnames=None):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(dict.fromkeys(k for row in rows for k in row))
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader(); writer.writerows(rows)
    os.replace(tmp, path)


def now():
    return datetime.now(timezone.utc).isoformat()


def environment():
    packages = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
                if d.metadata.get("Name")}
    return {"python": sys.version, "platform": platform.platform(),
            "machine": platform.machine(), "cpu_count": os.cpu_count(),
            "packages": dict(sorted(packages.items())),
            "thread_limits": {k: os.environ.get(k) for k in
                              ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}}


def code_snapshot():
    root = Path(__file__).resolve().parent
    files = sorted(p for p in root.rglob("*") if p.is_file() and
                   p.suffix in (".py", ".json", ".md", ".txt") and
                   "__pycache__" not in p.parts)
    inventory = [{"path": p.relative_to(root).as_posix(), "sha256": sha256(p)} for p in files]
    for label, source in (("Backend_init.py", root.parents[1]/"__init__.py"),
                          ("Backend_Benchmark_init.py", root.parent/"__init__.py")):
        if source.is_file():
            inventory.append({"path": "__package_parents__/"+label, "sha256": sha256(source),
                              "source_relative_to_repo": source.relative_to(root.parent.parent.parent).as_posix()})
    # Restrict Git metadata to this task. Never capture unrelated dirty IoT secrets.
    result = (subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             text=True, capture_output=True, check=False) if shutil.which("git") else None)
    return {"sha256": digest(inventory), "files": inventory,
            "git_commit": result.stdout.strip() if result is not None and result.returncode == 0 else None,
            "git_commit_is_not_a_substitute_for_snapshot": True}, root


class _Tee:
    def __init__(self, first, second):
        self.first, self.second = first, second

    def write(self, value):
        self.first.write(value); self.second.write(value)
        self.second.flush()
        return len(value)

    def flush(self):
        self.first.flush(); self.second.flush()


class RunStore:
    def __init__(self, root, config, argv=None, resume=False):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.config = config; self.config_sha = digest(config); self.resume = resume
        self.argv = list(sys.argv if argv is None else argv)
        self.invocation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self.invocation_path = self.root / "invocations" / (self.invocation_id + ".json")
        self.env = environment(); self.code, source = code_snapshot()
        self.env_sha = digest(self.env)
        lock = self.root / "STUDY_LOCK.json"
        if lock.exists() and json.loads(lock.read_text())["config_sha256"] != self.config_sha:
            raise ValueError("Config changed: choose a new --output-root; no mixed study results")
        if not lock.exists():
            atomic_json(lock, {"study_id": config["study_id"], "config_sha256": self.config_sha,
                               "created_at_utc": now()})
        dest = self.root / "code_snapshots" / self.code["sha256"]
        for item in self.code["files"]:
            target = dest / item["path"]
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                origin = (source.parents[2] / item["source_relative_to_repo"]
                          if "source_relative_to_repo" in item else source / item["path"])
                target.write_bytes(origin.read_bytes())
            if sha256(target) != item["sha256"]:
                raise ValueError("Stored code snapshot changed")
        atomic_json(dest / "SNAPSHOT.json", self.code)
        self.invocation = {"invocation_id": self.invocation_id, "argv": self.argv,
                           "cwd": str(Path.cwd()), "started_at_utc": now(),
                           "finished_at_utc": None, "return_code": None}
        atomic_json(self.invocation_path, self.invocation)

    def finish_invocation(self, return_code):
        self.invocation.update(finished_at_utc=now(), return_code=int(return_code))
        atomic_json(self.invocation_path, self.invocation)

    def active_units(self, stage=None):
        path = self.root / "ACTIVE_GRAPH.json"
        graph = json.loads(path.read_text()) if path.exists() else {}
        result = []
        for record in graph.values():
            if stage is not None and record["stage"] != stage:
                continue
            if record["code_sha256"] == self.code["sha256"] and record["config_sha256"] == self.config_sha and record.get("environment_sha256") == self.env_sha:
                unit = self.root / record["relative_path"]
                verify_ready(unit); result.append(unit)
        return sorted(result)

    def invalidate(self, stage, key):
        """Remove current pointers and descendants; retain immutable evidence."""
        path = self.root / "ACTIVE_GRAPH.json"
        if not path.exists():
            return
        graph = json.loads(path.read_text()); node_key = stage + ":" + key
        old = graph.pop(node_key, None)
        if old is None:
            return
        obsolete = [str((self.root / old["relative_path"]).resolve())]
        changed = True
        while changed:
            changed = False
            for child_key, record in list(graph.items()):
                mpath = self.root / record["relative_path"] / "run_manifest.json"
                manifest = json.loads(mpath.read_text())
                if any(str(Path(dep["path"]).resolve()).startswith(parent + os.sep)
                       for dep in manifest["input_artifacts"] for parent in obsolete):
                    obsolete.append(str(mpath.parent.resolve()))
                    del graph[child_key]; changed = True
        atomic_json(path, graph)

    def invalidate_changed_attempt(self, stage, key, signature):
        path = self.root / "ACTIVE_GRAPH.json"
        graph = json.loads(path.read_text()) if path.exists() else {}
        old = graph.get(stage + ":" + key)
        if old is not None:
            mpath = self.root / old["relative_path"] / "run_manifest.json"
            if json.loads(mpath.read_text())["signature"] != signature:
                self.invalidate(stage, key)

    def _activate(self, run):
        path = self.root / "ACTIVE_GRAPH.json"
        graph = json.loads(path.read_text()) if path.exists() else {}
        node_key = run.stage + ":" + run.key
        previous = graph.get(node_key)
        unchanged = previous is not None and previous["relative_path"] == str(run.path.relative_to(self.root))
        obsolete = [] if previous is None or unchanged else [str((self.root / previous["relative_path"]).resolve())]
        # Invalidate pointers to descendants of replaced inputs; files stay intact.
        changed = True
        while changed:
            changed = False
            for key, record in list(graph.items()):
                manifest_path = self.root / record["relative_path"] / "run_manifest.json"
                manifest = json.loads(manifest_path.read_text())
                if key != node_key and any(
                        str(Path(dep["path"]).resolve()).startswith(old + os.sep)
                        for dep in manifest["input_artifacts"] for old in obsolete):
                    obsolete.append(str(manifest_path.parent.resolve()))
                    del graph[key]; changed = True
        graph[node_key] = {"stage": run.stage, "key": run.key,
                           "relative_path": str(run.path.relative_to(self.root)),
                           "code_sha256": self.code["sha256"], "config_sha256": self.config_sha,
                           "environment_sha256": self.env_sha}
        atomic_json(path, graph)

    def unit(self, stage, key, parents=(), extra=None):
        inputs = [{"path": str(Path(p).resolve()), "sha256": sha256(p)} for p in parents]
        signature = digest({"stage": stage, "key": key, "config": self.config_sha,
                            "code": self.code["sha256"], "environment": digest(self.env),
                            "inputs": inputs, "extra": extra})
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in key)[:100]
        base = self.root / stage / (safe + "__" + signature[:16])
        complete = base / "READY.json"
        if complete.exists():
            if not self.resume:
                raise FileExistsError(f"Completed unit exists; use --resume: {base}")
            verify_ready(base)
            return Unit(self, base, stage, key, signature, inputs, reused=True)
        if base.exists():
            # An interrupted/failed attempt stays immutable; retry in a sibling.
            siblings = sorted(base.parent.glob(base.name + "__attempt_*"))
            for sibling in reversed(siblings):
                if (sibling / "READY.json").exists() and self.resume:
                    verify_ready(sibling)
                    return Unit(self, sibling, stage, key, signature, inputs, reused=True)
            if not self.resume:
                raise FileExistsError(f"Incomplete unit exists; inspect it or use --resume: {base}")
            base = base.with_name(base.name + "__attempt_" + uuid.uuid4().hex[:8])
        return Unit(self, base, stage, key, signature, inputs)

    def update_indexes(self, run):
        lock = self.root / ".index_writer.lock"
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.close(fd)
            path = self.root / "RUN_INDEX.csv"
            rows = []
            if path.exists():
                with path.open(encoding="utf-8", newline="") as f:
                    rows = list(csv.DictReader(f))
            item = {"run_id": run.manifest["run_id"], "stage": run.stage, "unit_key": run.key,
                    "execution_status": run.manifest["execution_status"],
                    "scientific_support_status": run.manifest["scientific_support_status"],
                    "started_at_utc": run.manifest["started_at_utc"],
                    "finished_at_utc": run.manifest["finished_at_utc"],
                    "code_sha256": self.code["sha256"], "config_sha256": self.config_sha,
                    "relative_path": str(run.path.relative_to(self.root)),
                    "summary_path": str((run.path / "SUMMARY.md").relative_to(self.root))}
            rows = [r for r in rows if r["run_id"] != item["run_id"]] + [item]
            atomic_csv(path, rows)
            # Root artifact index points to per-run indexes, without opening NPZ/models.
            atomic_csv(self.root / "ARTIFACT_INDEX.csv", [
                {"run_id": r["run_id"], "execution_status": r["execution_status"],
                 "artifact_index_path": r["relative_path"] + "/artifact_index.csv"} for r in rows])
            atomic_json(self.root / "LATEST.json", item)
            if run.manifest["execution_status"] == "complete":
                self._activate(run)
        finally:
            lock.unlink(missing_ok=True)


def verify_ready(path):
    path = Path(path)
    record = json.loads((path / "READY.json").read_text(encoding="utf-8"))
    for item in record["files"]:
        f = path / item["path"]
        if not f.is_file() or f.stat().st_size != item["bytes"] or sha256(f) != item["sha256"]:
            raise ValueError(f"Completed artifact changed/missing: {f}")
    return record


class Unit:
    def __init__(self, store, path, stage, key, signature, inputs, reused=False):
        self.store, self.path, self.stage, self.key = store, path, stage, key
        self.signature, self.inputs, self.reused = signature, inputs, reused
        self.required = []; self.accepted = False
        self.manifest = {}

    def __enter__(self):
        if self.reused:
            self.manifest = json.loads((self.path / "run_manifest.json").read_text())
            self.store.update_indexes(self)
            return self
        self.store.invalidate_changed_attempt(self.stage, self.key, self.signature)
        self.path.mkdir(parents=True, exist_ok=False); self.started = time.perf_counter()
        self.manifest = {"schema_version": "csv_npz_v1", "run_id": self.path.name,
                         "stage": self.stage, "unit_key": self.key, "signature": self.signature,
                         "study_id": self.store.config["study_id"], "execution_status": "running",
                         "scientific_support_status": "not_audited", "started_at_utc": now(),
                         "config_sha256": self.store.config_sha, "code_sha256": self.store.code["sha256"],
                         "environment_sha256": self.store.env_sha,
                         "input_artifacts": self.inputs, "error": None}
        self.json("run_manifest.json", self.manifest)
        self.json("config.resolved.json", self.store.config)
        self.json("environment.json", self.store.env)
        self.json("source_snapshot.json", self.store.code)
        self.json("command.json", {"argv": self.store.argv, "cwd": str(Path.cwd()), "unit_return_code": None,
                                    "invocation_receipt": str(self.store.invocation_path)})
        self.stack = ExitStack()
        stdout = self.stack.enter_context((self.path / "stdout.log").open("w", encoding="utf-8"))
        stderr = self.stack.enter_context((self.path / "stderr.log").open("w", encoding="utf-8"))
        self.stack.enter_context(redirect_stdout(_Tee(sys.stdout, stdout)))
        self.stack.enter_context(redirect_stderr(_Tee(sys.stderr, stderr)))
        print(f"BEGIN {self.stage} {self.key} -> {self.path}", flush=True)
        return self

    def json(self, name, value):
        atomic_json(self.path / name, value)

    def csv(self, name, rows, fieldnames=None):
        atomic_csv(self.path / name, rows, fieldnames)

    def accept(self, required, metrics, summary, support="adequate_for_declared_scope"):
        self.required = list(required); self.accepted = True
        self.manifest["scientific_support_status"] = support
        self.json("metrics.json", metrics)
        (self.path / "SUMMARY.md").write_text(summary.rstrip() + "\n", encoding="utf-8")
        self.json("validation.json", {"status": "passed", "required_outputs": self.required})

    def __exit__(self, exc_type, exc, tb):
        if self.reused:
            return False
        if exc is not None:
            traceback.print_exception(exc_type, exc, tb, file=sys.stderr)
        self.stack.close()
        missing = [name for name in self.required if not (self.path / name).is_file()]
        valid = exc is None and self.accepted and not missing
        self.manifest.update(execution_status="complete" if valid else "failed",
                             finished_at_utc=now(), wall_seconds=time.perf_counter()-self.started,
                             peak_rss_bytes=None, memory_measurement_method=None)
        if not valid:
            self.manifest["error"] = {"type": exc_type.__name__ if exc_type else "IncompleteOutputs",
                                      "message": str(exc) if exc else f"Unaccepted/missing outputs: {missing}"}
            if exc_type is not None and exc_type.__name__ == "FailedSupport":
                self.manifest["scientific_support_status"] = "failed_support"
            self.json("validation.json", {"status": "failed", "missing_outputs": missing,
                                           "error": self.manifest["error"]})
            if not (self.path / "SUMMARY.md").exists():
                (self.path / "SUMMARY.md").write_text("Execution failed; see run_manifest.json and stderr.log.\n")
            if not (self.path / "metrics.json").exists():
                self.json("metrics.json", {"execution_status": "failed"})
        self.json("run_manifest.json", self.manifest)
        self.json("command.json", {"argv": self.store.argv, "cwd": str(Path.cwd()),
                                    "unit_return_code": 0 if valid else 1,
                                    "invocation_receipt": str(self.store.invocation_path)})
        files = [{"path": p.relative_to(self.path).as_posix(), "bytes": p.stat().st_size,
                  "sha256": sha256(p)} for p in sorted(self.path.rglob("*")) if p.is_file()
                 and p.name not in ("READY.json", "artifact_index.csv")]
        self.csv("artifact_index.csv", files)
        files.append({"path": "artifact_index.csv", "bytes": (self.path / "artifact_index.csv").stat().st_size,
                      "sha256": sha256(self.path / "artifact_index.csv")})
        if valid:
            self.json("READY.json", {"signature": self.signature, "files": files, "created_at_utc": now()})
        self.store.update_indexes(self)
        if exc is None and not valid:
            raise RuntimeError(f"Unit did not complete validation: {self.path}")
        return False
