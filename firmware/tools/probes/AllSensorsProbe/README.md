# AllSensorsProbe

Serial-only integration harness for the currently available sensors:

- NPK over the configured RS485/Modbus UART;
- SHT30 over the configured I2C pins;
- DS18B20 over GPIO21, injected into the existing NPK temperature field;
- capacitive moisture v1.2 over analog GPIO1, injected into the existing NPK
  humidity field when its two-point relative calibration is valid.

The harness uses the reusable sensor services and `NodePacketBuilder`, prints
the combined production-shaped packet, and deliberately does not initialize
the modem, Firebase, offline storage, or deep sleep. It is selected by
`APP_ALL_SENSORS_TEST_MODE`.
