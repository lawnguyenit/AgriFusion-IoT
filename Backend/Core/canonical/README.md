# Canonical Tables

`canonical/` chua cac builders tao bang chuan cho model consumers.

Hien tai `tabnet_super_table.py` doc truc tiep:

```text
Output_data/SuperTable/super_table.csv
```

va tao:

```text
Output_data/TabNet/tabnet_matrix.csv
Output_data/TabNet/tabnet_schema.json
```

Package nay khong phu thuoc vao `tabnet_ready.csv`, `present__*`, `health`, `handoff`, hoac `confidence`. Cac field do da bi loai khoi contract moi.

Chay tu thu muc `Backend`:

```powershell
python Core\canonical\tabnet_super_table.py
```
