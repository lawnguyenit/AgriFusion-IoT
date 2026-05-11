from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.fuzzy_logic_basic.layer1.main import build_config, parse_args, run_alignment  # noqa: E402
from Backend.Benchmark.fuzzy_logic_basic.layer15.main import build_event_annotations  # noqa: E402
from Backend.Benchmark.fuzzy_logic_basic.layer2.main import build_membership  # noqa: E402
from Backend.Benchmark.fuzzy_logic_basic.layer3.main import build_pressure  # noqa: E402
from Backend.Benchmark.fuzzy_logic_basic.layer35.main import build_temporal_dynamics  # noqa: E402
from Backend.Benchmark.fuzzy_logic_basic.layer4.main import build_prediction_output  # noqa: E402
from Backend.Benchmark.fuzzy_logic_basic.layer5.main import build_pathway_interpretation  # noqa: E402


def main() -> None:
    args = parse_args()
    config = build_config(args)

    layer1_result = run_alignment(config=config, limit=args.limit)
    layer15_result = build_event_annotations(input_csv=layer1_result.csv_path)
    membership_result = build_membership(input_csv=layer15_result.output_csv)
    pressure_result = build_pressure(input_csv=membership_result.output_csv)
    dynamics_result = build_temporal_dynamics(input_csv=pressure_result.output_csv)
    prediction_result = build_prediction_output(
        membership_csv=membership_result.output_csv,
        pressure_csv=pressure_result.output_csv,
        dynamics_csv=dynamics_result.output_csv,
    )
    pathway_result = build_pathway_interpretation(
        output_csv=prediction_result.output_csv,
        pressure_csv=pressure_result.output_csv,
        dynamics_csv=dynamics_result.output_csv,
    )

    print("FLB pipeline complete")
    print(f"Layer1 CSV: {layer1_result.csv_path}")
    print(f"Layer1.5 CSV: {layer15_result.output_csv}")
    print(f"Layer2 CSV: {membership_result.output_csv}")
    print(f"Layer3 CSV: {pressure_result.output_csv}")
    print(f"Layer3.5 CSV: {dynamics_result.output_csv}")
    print(f"Layer4 CSV: {prediction_result.output_csv}")
    print(f"Layer5 CSV: {pathway_result.output_csv}")
    print(
        "Rows: "
        f"layer1={layer1_result.row_count}, "
        f"layer1.5={layer15_result.row_count}, "
        f"layer2={membership_result.row_count}, "
        f"layer3={pressure_result.row_count}, "
        f"layer3.5={dynamics_result.row_count}, "
        f"layer4={prediction_result.row_count}, "
        f"layer5={pathway_result.row_count}"
    )


if __name__ == "__main__":
    main()
