# Soilv2

Purpose: simple analog soil moisture helper with calibration points.

Main API:
- `SoilV2::begin()`
- `SoilV2::read()`

What it returns:
- Raw ADC value
- Percentage estimate
- Simple wet/dry state string

Status:
- Utility library kept for alternate soil probes, not the main NPK path.
