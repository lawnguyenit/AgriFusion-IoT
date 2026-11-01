# SHT30 Raw Wire Probe

## Current checkout status

This directory contains a standalone diagnostic implementation, but the
current firmware does **not** select or call it. `IoT_Node/src/main.cpp` is a
thin wrapper around `AppEntry`; `IoT_Node/lib/AppEntry/src/AppEntry.cpp` has no
`Sht30RawProbe` include, call, or compile-time selector. Do not infer that a
firmware build or board is currently running this probe.

As checked on 2026-10-08, `Sht30RawProbe.cpp` soft-resets the sensor once at
startup, checks the configured address, and then periodically sends only
`0x2C06` (high repeatability with clock stretching). It reads the six-byte
response, checks the temperature and humidity CRCs separately, and prints the
raw words and decoded values. It does not implement the no-stretch `0x2400`
comparison in the current source. The requested two-mode comparison is
therefore incomplete in this checkout.

## Isolation and safety

If this probe is integrated into an explicit diagnostic-only entry point, it
should continue to use Arduino `Wire` directly and stay outside
`Sht30Service`, Adafruit `readBoth()`, Firebase, and the production packet
path. Restore/select the production `AppEntry` path before normal device use.
The current source's presence alone does not change the production path.

A CRC-valid zero frame (`00 00 81 00 00 81`) is protocol-consistent data. It
shows what the sensor returned, but does not by itself prove a new physical
conversion or distinguish a sensor fault from an environmental condition.

The 2026-10-05 PlatformIO build and hardware observations recorded in the
dated worklog describe that checkout at that time; they do not verify the
current source tree. Rebuild and obtain a new serial log after wiring the
probe into a diagnostic entry point.
