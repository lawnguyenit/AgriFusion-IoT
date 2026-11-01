# NpkMatrixProbe

Thin AppEntry adapter for a one-shot NPK-only bench run. It owns `Serial1`,
instantiates `NpkMatrixTest`, and launches the read-only Modbus matrix once
during setup. The matrix logic and per-case reporting remain in
`NpkMatrixTest`; no sensor-specific behavior is duplicated here.

Selected with `APP_NPK_MATRIX_TEST_MODE=1`. The adapter skips the normal
`AppRuntime` path and returns after the matrix completes. See
[`NpkMatrixTest`](../NpkMatrixTest/README.md) for UART, wiring, and result
interpretation.
