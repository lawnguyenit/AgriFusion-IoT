# NpkMatrixTest

Temporary diagnostic-only NPK/RS485 parameter matrix.

The module uses the existing `NPK_RX_PIN`, `NPK_TX_PIN`, and `NPK_BAUDRATE`
configuration as the baseline. It then checks the requested soil attributes
independently: humidity, temperature, EC, pH, nitrogen, phosphorus, and
potassium. Each case prints a stable case number, baud/format, slave ID,
function code, register address, quantity, raw response words, and a candidate
conversion hint.

The first candidate family follows the JXBS/JXCT-style sparse map:

The source used for these candidates is the manufacturer-hosted [JXBS-3001-TR
RS485 instruction manual](https://jxctsmart.com/wp-content/uploads/2022/10/Soil-Hygrometer-Introduction-Manual.pdf).
It is a close family reference, not proof that the unlabeled unit in the photo
uses exactly the same firmware map.

- pH: `0x0006`, raw `/100` as the primary interpretation;
- soil humidity and temperature: `0x0012` and `0x0013`, raw `/10`;
- EC: `0x0015`, direct raw value;
- N/P/K: `0x001E..0x0020`, direct raw values.

The older contiguous `0x0000..0x0006` map is retained as a separate variant
candidate because it was used by the earlier firmware. The baud profile is
fixed to the already confirmed production value, currently `9600 8N1`, so the
matrix does not spend time retesting known baud alternatives. FC03 is tested
first; FC04 is tested as a read-only fallback. If no protocol evidence appears,
the matrix expands the slave ID probe from `1` through `10`.

This is only a protocol/value-discovery aid. A successful Modbus frame proves
that a device answered that transaction; it does not by itself prove that the
decoded value is physically meaningful. Test with the probe powered and
inserted into soil when validating soil measurements. The matrix never writes
configuration registers, does not change production pin settings, and must
not be used as the production sensor implementation.
