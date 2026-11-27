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
- Reused by the temporary `SoilMoistureProbe` analog diagnostic.
- It remains outside the main NPK path until a physical calibration and
  integration decision are confirmed.
