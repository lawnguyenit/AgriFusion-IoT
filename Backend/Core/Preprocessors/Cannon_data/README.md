# Cannon_data

`Cannon_data` builds model-facing canonical tables from Layer 2.5 outputs.

## Purpose

This package converts `super_table/tabnet_ready.csv` into a TabNet-friendly matrix by:

- dropping high-cardinality text/path columns that are not useful as direct model inputs,
- encoding boolean and categorical columns into integer IDs,
- imputing missing numeric values with per-column medians,
- adding cyclic time features from `ts_hour_bucket`,
- writing a schema file so feature-to-agent mappings can be traced later.

## Run

From `Backend`:

```powershell
python Core\Cannon_data\tabnet_super_table.py
```

Default input:

- `Backend/Output_data/Layer2.5/super_table/tabnet_ready.csv`

Default outputs:

- `Backend/Output_data/TabNet/tabnet_matrix.csv`
- `Backend/Output_data/TabNet/tabnet_schema.json`

## Optional Label

If you already know a target column, pass it explicitly:

```powershell
python Core\Cannon_data\tabnet_super_table.py --label-column npk__npk_7in1_1__flags__nutrient_imbalance
```

When no label is provided, the output matrix only contains features + `ts_hour_bucket`.
That is suitable for representation/pretraining steps or relation-mining before domain-agent fusion.
