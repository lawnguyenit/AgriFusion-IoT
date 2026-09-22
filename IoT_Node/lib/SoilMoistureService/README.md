# SoilMoistureService

Reusable analog service for the capacitive moisture v1.2 module.

The service owns ADC sampling and applies the manufacturer's two-point
relative-moisture procedure. The configured dry and wet endpoints are local
calibration inputs; no universal ADC pair is assumed. If those endpoints are
unset, raw ADC, range, millivolts, and the `uncalibrated` state are still
reported while percentage remains invalid.

The current Node2 profile enables a provisional relative index derived from
the manufacturer's example range, scaled from Arduino's 10-bit ADC to the
ESP32's 12-bit ADC and direction-adjusted to match the observed unit:
`dry_adc=1041`, `wet_adc=2082`. This is explicitly marked
`provisional_default` and `relative_index_0_100_not_vwc`; it is not a field
calibration. The nominal installation depth is 10 cm (the retained operating
range is 10-15 cm from the probe tip).

Every NPK payload also carries a `moisture_calibration` object containing the
active profile, endpoint pair, depth, latest raw/mV observation, percentage,
state, and error. Replace the provisional endpoints after collecting paired
field observations at the actual installation depth.

`AppRuntime` and `AllSensorsProbe` use this service and inject a valid
percentage into the existing NPK humidity field. The service does not create
a separate canonical moisture sensor branch.
