from pathlib import Path
from Backend.Config.IO.io_csv import SourceSpec, convert_multi_jsonl_to_csv
import Backend.Config.path_manager as pm
import Benchmark.Tabnet_vanilla.config.settings as settings

def main() -> None:
    npk_json    = pm.get_json_npk_path()
    sht30_json  = pm.get_json_sht30_path()
    meteo_json  = pm.get_json_meteo_path()
    output_path = Path(__file__).parent / "Input"

    specs = [
        SourceSpec(
            name="npk",
            path=npk_json,
            fields=settings.NPK_FIELDS,
        ),
        SourceSpec(
            name="sht",
            path=sht30_json,
            fields=settings.SHT_FIELDS,
        ),
        SourceSpec(
            name="meteo",
            path=meteo_json,
            fields=settings.METEO_FIELDS,
        ),
    ]
    
    df = convert_multi_jsonl_to_csv(specs, output_path)
    print(df.head())
    print(df.shape)



if __name__ == "__main__":
    main()
