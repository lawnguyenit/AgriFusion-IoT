from __future__ import annotations

import argparse
from pathlib import Path


from agrifusion_research.core.protocol_registry import build_protocol_registry
from agrifusion.settings.paths import BACKEND_PATHS
from agrifusion_research.core.common.paths import PROTOCOL_REGISTRY_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the upstream Phase A protocol registry.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config" / "protocol_v1.yaml",
    )
    parser.add_argument(
        "--layer1-manifest",
        type=Path,
        default=BACKEND_PATHS.layer1_dir / "manifest.json",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROTOCOL_REGISTRY_ROOT / "artifacts",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = build_protocol_registry(args.config, args.layer1_manifest, output_root=args.output_root)
    print("protocol_registry build complete")
    print(f"Output dir: {run_dir}")


if __name__ == "__main__":
    main()
