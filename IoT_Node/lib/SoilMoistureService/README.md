# SoilMoistureService

Reusable analog service for the capacitive moisture v1.2 module.

The service owns ADC sampling and applies a two-point relative-index
procedure. The configured dry and wet endpoints are local calibration inputs;
no universal ADC pair is assumed. If those endpoints are
unset, raw ADC, range, millivolts, and the `uncalibrated` state are still
reported while percentage remains invalid.

The current Node2 profile uses a provisional reference pair for the common
capacitive v1.2 probe: `dry_adc=3000` in air and `wet_adc=1200` submerged,
from the [ShillehTek v1.2 ESP32 manual](https://shillehtek.com/blogs/shillehtek-product-manuals/capacitive-soil-moisture-sensor-v1-2-manual).
That manual reports about 2.5 V in air and 1.0 V submerged; the user's air
reading (`raw≈2967`, `2508 mV`) is consistent with its 12-bit ESP32 dry example.
This is explicitly marked `provisional_default` and
`relative_index_0_100_not_vwc`; it is not a field calibration. The reference
normalizes from air to submerged water, not from agronomic dry soil to saturated
soil. The 30/70 state bands are software defaults, not recommendations from the
manual. Do not interpret `UOT` as flooding without a separate water-level test.
The nominal installation depth is 10 cm (the retained operating range is 10-15
cm from the probe tip).

Every NPK payload also carries a `moisture_calibration` object containing the
active profile, endpoint pair, depth, latest raw/mV observation, percentage,
state, and error. Replace the provisional endpoints after collecting paired
field observations at the actual installation depth.

`AppRuntime` and `AllSensorsProbe` use this service and inject a valid
percentage into the existing NPK humidity field. The service does not create
a separate canonical moisture sensor branch.
