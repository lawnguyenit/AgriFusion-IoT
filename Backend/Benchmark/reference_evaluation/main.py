"""Executable entry point. Thread limits are applied before numeric imports."""
import argparse
import json
import os
from pathlib import Path
import sys


def parser():
    p = argparse.ArgumentParser(description="Recorded-reference comparison; no Firebase/firmware calls")
    p.add_argument("command", choices=("audit","validate","smoke","fit","evaluate","sensitivity","solver","report","export","all"))
    p.add_argument("--config", default="Backend/Benchmark/reference_evaluation/configs/recorded_hourly_v1.json")
    p.add_argument("--output-root")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--download", action="store_true", help="Explicit official-source download; audit command only")
    p.add_argument("--dataset", action="append", choices=("beijing_multi_site_501","appliances_energy_374"))
    p.add_argument("--fixture-dir", help="Directory holding the sixteen delivered Jena fixture files")
    p.add_argument("--unit-only", action="store_true", help="validate only: unit tests, does NOT pass the full P2 gate")
    p.add_argument("--without-audit-truth", action="store_true", help="export only: omit audit_only subdirectories")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.download and args.command != "audit":
        parser().error("--download is permitted only for explicit audit")
    if args.unit_only and args.command != "validate":
        parser().error("--unit-only applies only to validate, not the main experiment")
    cfg_path = Path(args.config)
    config = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
        os.environ[name] = str(config["resources"]["threads"])
    from .config import validate_config
    from .pipeline import Pipeline
    from .storage import RunStore
    validate_config(config)
    root = args.output_root or config["paths"]["output_root"]
    store = RunStore(root, config, argv=[sys.executable,"-m","Backend.Benchmark.reference_evaluation.main"]+
                     (list(argv) if argv is not None else sys.argv[1:]), resume=args.resume)
    pipeline = Pipeline(store, args.dataset); return_code = 1
    try:
        command = args.command
        if command == "audit":
            pipeline.audit(args.download)
        elif command == "validate":
            pipeline.validate(args.fixture_dir,args.unit_only)
        elif command == "all":
            print("LOCAL EXPORT:",pipeline.all(args.fixture_dir))
        elif command == "export":
            print("LOCAL EXPORT (not yet uploaded):",pipeline.export(args.without_audit_truth))
        else:
            getattr(pipeline,command)()
        return_code = 1 if pipeline.errors else 0
        return return_code
    except KeyboardInterrupt:
        return_code=130
        print('Interrupted; incomplete units are preserved for --resume.',file=sys.stderr)
        return return_code
    finally:
        store.finish_invocation(return_code)


if __name__ == "__main__":
    raise SystemExit(main())
