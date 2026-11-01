# SIM UART loopback probe

This diagnostic checks the ESP32-S3 UART2 transmit/receive path only. It does
not send AT commands, initialize the modem, connect to a network, or write to
Node2.

Before powering the board, disconnect the modem and the level shifter from the
UART pins, then jumper ESP GPIO17 (TX) directly to GPIO16 (RX). Keep the board's
normal ground and power wiring unchanged. The test sends a known byte pattern
at the configured `SIM_BAUDRATE` and checks whether the same bytes return.

- `pass=1` means the ESP UART configuration and direct GPIO loopback work.
- `pass=0` means the direct loopback was not received correctly; inspect the
  jumper and the selected ESP pins before testing the modem again.

The test repeats once per second. A passing direct loopback does not validate
the level shifter or A7680C; those can be tested separately after this baseline
passes.
