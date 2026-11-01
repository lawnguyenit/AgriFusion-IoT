# AppEntry

Purpose: keep `src/main.cpp` disposable by moving mode selection and app startup into a library entrypoint.

`AppEntry` dispatches by the compile-time selectors in `Config.h`. In the
current production profile, all diagnostic selectors are off, so `AppEntry`
starts `AppRuntime` and the Node2 telemetry path. Set
`APP_NPK_MATRIX_TEST_MODE=1` to run the dedicated serial-only read-only Modbus
matrix instead.

Responsibilities:
- initialize debug serial once
- select between the SIM-to-Node2 debug write, SIM UART loopback, serial-only sensor probes, optional moisture-v1.2/SHT30/DS18B20/`RawTruthProbe` diagnostics, and the real `AppRuntime` path, where `Ds18b20Service` and `SoilMoistureService` are part of the normal NPK collection pipeline
- keep `main.cpp` as a thin wrapper only

`APP_SIM_NODE2_TEST_MODE=1` is an opt-in diagnostic. It uses `SimNode2Probe`
to test modem HTTP and make a SIM-backed RTDB write to
`/debug/Node2/telemetry_probe`, retrying failed attempts every 5 seconds until
the first successful write. It is disabled in the production configuration.
The separate `APP_SIM_UART_LOOPBACK_TEST_MODE=1` selector tests UART2 TX/RX
with a local jumper and skips modem communication, network, and RTDB.

The opt-in NPK test uses the standard `esp32-s3-n16r8` PlatformIO environment.
It runs `NpkMatrixTest` once at boot using the configured 9600 8N1 UART
(ESP RX GPIO4 / TX GPIO5), performs only Modbus reads, and does not start
other sensors, SIM/Firebase, or production runtime. See the
[NpkMatrixTest README](../NpkMatrixTest/README.md) for tested maps and result
interpretation. Leave the selector at 0 after the bench test to restore
production behavior.

`Sht30RawProbe` is a separate direct-Wire source and is not currently included
or invoked by `AppEntry`; it is not one of the active compile-time selectors.

Main files:
- `src/AppEntry.h`
- `src/AppEntry.cpp`
