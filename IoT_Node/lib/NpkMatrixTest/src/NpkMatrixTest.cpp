#include "NpkMatrixTest.h"

#include <ModbusMaster.h>

#include "Config.h"
#include "NPK.h"

const NpkMatrixTest::MatrixTransport NpkMatrixTest::TRANSPORTS[MATRIX_TRANSPORT_COUNT] = {
    {"configured", NPK_BAUDRATE, SERIAL_8N1, "8N1"},
};

const NpkMatrixTest::MatrixMap NpkMatrixTest::MAP_CANDIDATES[MATRIX_MAP_COUNT] = {
    {"legacy_full_7in1", 0x03, 0x0000, 7U,
     "hum=r0/10,temp=r1/10,ec=r2,ph=r3/10,N=r4,P=r5,K=r6"},
    {"jxct_ph", 0x03, 0x0006, 1U,
     "ph=raw/100 (alternate hypothesis raw/10)"},
    {"jxct_moisture", 0x03, 0x0012, 1U,
     "soil_hum=raw/10"},
    {"jxct_temperature", 0x03, 0x0013, 1U,
     "soil_temp=signed_raw/10"},
    {"jxct_moist_temp", 0x03, 0x0012, 2U,
     "soil_hum=r0/10,soil_temp=signed_r1/10"},
    {"jxct_ec", 0x03, 0x0015, 1U,
     "soil_ec=raw"},
    {"jxct_npk", 0x03, 0x001E, 3U,
     "N=r0,P=r1,K=r2"},
    {"jxct_nitrogen", 0x03, 0x001E, 1U,
     "N=raw"},
    {"jxct_phosphorus", 0x03, 0x001F, 1U,
     "P=raw"},
    {"jxct_potassium", 0x03, 0x0020, 1U,
     "K=raw"},
    {"legacy_humidity", 0x03, 0x0000, 1U,
     "soil_hum=raw/10"},
    {"legacy_temperature", 0x03, 0x0001, 1U,
     "soil_temp=signed_raw/10"},
    {"legacy_ec", 0x03, 0x0002, 1U,
     "soil_ec=raw"},
    {"legacy_ph", 0x03, 0x0003, 1U,
     "ph=raw/10 (alternate hypothesis raw/100)"},
    {"legacy_npk", 0x03, 0x0004, 3U,
     "N=r0,P=r1,K=r2"},
};

NpkMatrixTest::NpkMatrixTest(HardwareSerial &serial) : _serial(serial) {}

void NpkMatrixTest::activateTransport(uint8_t transportIndex) {
    const MatrixTransport &transport = TRANSPORTS[transportIndex];
    if (_activeTransport == &transport) {
        return;
    }

    if (_activeTransport != nullptr) {
        _serial.end();
        delay(40);
    }

    _serial.begin(transport.baud,
                 transport.serialConfig,
                 NPK_RX_PIN,
                 NPK_TX_PIN);
    _serial.setTimeout(50);
    _activeTransport = &transport;

    CUS_DBGF("[NPK][MATRIX] UART switched profile=%s baud=%lu format=%s rx=%d tx=%d\n",
             transport.name,
             (unsigned long)transport.baud,
             transport.format,
             NPK_RX_PIN,
             NPK_TX_PIN);
}

void NpkMatrixTest::flushSerial() {
    while (_serial.available() > 0) {
        (void)_serial.read();
    }
}

const char *NpkMatrixTest::statusClass(uint8_t status) {
    if (status == ModbusMaster::ku8MBSuccess) {
        return "SUCCESS_VALID_FRAME";
    }
    if (status >= ModbusMaster::ku8MBIllegalFunction &&
        status <= ModbusMaster::ku8MBSlaveDeviceFailure) {
        return "RESPONSE_EXCEPTION";
    }
    if (status == ModbusMaster::ku8MBInvalidCRC) {
        return "RESPONSE_BAD_CRC";
    }
    if (status == ModbusMaster::ku8MBInvalidSlaveID ||
        status == ModbusMaster::ku8MBInvalidFunction) {
        return "RESPONSE_ID_OR_FUNCTION_MISMATCH";
    }
    if (status == ModbusMaster::ku8MBResponseTimedOut) {
        return "NO_COMPLETE_RESPONSE";
    }
    return "OTHER_MODBUS_RESULT";
}

bool NpkMatrixTest::hasBusEvidence(uint8_t status) {
    return status != ModbusMaster::ku8MBResponseTimedOut;
}

void NpkMatrixTest::rememberTarget(uint8_t transportIndex, uint8_t slaveId) {
    for (uint8_t i = 0; i < _targetCount; ++i) {
        if (_targets[i].transportIndex == transportIndex &&
            _targets[i].slaveId == slaveId) {
            return;
        }
    }

    if (_targetCount >= MATRIX_MAX_TARGETS) {
        return;
    }

    _targets[_targetCount++] = {transportIndex, slaveId};
}

void NpkMatrixTest::rememberHit(uint16_t caseNumber,
                                uint8_t transportIndex,
                                uint8_t slaveId,
                                const MatrixMap &map,
                                uint8_t status,
                                const char *stage) {
    if (_hitCount >= MATRIX_MAX_HITS) {
        _hitOverflow++;
        return;
    }

    _hits[_hitCount++] = {
        caseNumber,
        transportIndex,
        slaveId,
        map.functionCode,
        map.startAddress,
        map.quantity,
        status,
        stage,
        map.name};
}

uint8_t NpkMatrixTest::runCase(const char *stage,
                               uint8_t transportIndex,
                               uint8_t slaveId,
                               const MatrixMap &map) {
    activateTransport(transportIndex);
    flushSerial();

    ModbusMaster node;
    node.begin(slaveId, _serial);

    const uint16_t caseNumber = ++_caseCount;
    CUS_DBGF("[NPK][MATRIX][CASE %03u] stage=%s profile=%s baud=%lu format=%s slave=%u func=0x%02X start=0x%04X qty=%u map=%s\n",
             (unsigned)caseNumber,
             stage,
             TRANSPORTS[transportIndex].name,
             (unsigned long)TRANSPORTS[transportIndex].baud,
             TRANSPORTS[transportIndex].format,
             (unsigned)slaveId,
             (unsigned)map.functionCode,
             (unsigned)map.startAddress,
             (unsigned)map.quantity,
             map.name);

    const uint32_t startMs = millis();
    uint8_t status = ModbusMaster::ku8MBResponseTimedOut;
    if (map.functionCode == 0x04) {
        status = node.readInputRegisters(map.startAddress, map.quantity);
    } else {
        status = node.readHoldingRegisters(map.startAddress, map.quantity);
    }
    const uint32_t durationMs = millis() - startMs;
    const bool busEvidence = hasBusEvidence(status);

    if (status == ModbusMaster::ku8MBSuccess) {
        _successCount++;
        CUS_DBGF("[NPK][MATRIX][RESULT %03u] class=%s status=0x%02X duration=%lu ms map=%s decode=%s raw=",
                 (unsigned)caseNumber,
                 statusClass(status),
                 (unsigned)status,
                 (unsigned long)durationMs,
                 map.name,
                 map.decodeHint);
        for (uint8_t i = 0; i < map.quantity; ++i) {
            CUS_DBGF(" %u:0x%04X", (unsigned)i, (unsigned)node.getResponseBuffer(i));
        }
        CUS_DBGLN("");
    } else {
        if (status >= ModbusMaster::ku8MBIllegalFunction &&
            status <= ModbusMaster::ku8MBSlaveDeviceFailure) {
            _exceptionCount++;
        } else if (status != ModbusMaster::ku8MBResponseTimedOut) {
            _frameErrorCount++;
        } else {
            _timeoutCount++;
        }

        CUS_DBGF("[NPK][MATRIX][RESULT %03u] class=%s status=0x%02X (%s) duration=%lu ms bus_evidence=%d\n",
                 (unsigned)caseNumber,
                 statusClass(status),
                 (unsigned)status,
                 MyNPK::errorCodeToString(status),
                 (unsigned long)durationMs,
                 busEvidence ? 1 : 0);
    }

    if (busEvidence) {
        rememberTarget(transportIndex, slaveId);
        rememberHit(caseNumber, transportIndex, slaveId, map, status, stage);
    }

    return status;
}

void NpkMatrixTest::resetState() {
    _activeTransport = nullptr;
    _targetCount = 0;
    _hitCount = 0;
    _hitOverflow = 0;
    _caseCount = 0;
    _successCount = 0;
    _exceptionCount = 0;
    _frameErrorCount = 0;
    _timeoutCount = 0;
}

void NpkMatrixTest::printSummary() {
    CUS_DBGF("\n[NPK][MATRIX][SUMMARY] cases=%u success=%u exceptions=%u frame_errors=%u timeouts=%u targets=%u hit_records=%u overflow=%u\n",
             (unsigned)_caseCount,
             (unsigned)_successCount,
             (unsigned)_exceptionCount,
             (unsigned)_frameErrorCount,
             (unsigned)_timeoutCount,
             (unsigned)_targetCount,
             (unsigned)_hitCount,
             (unsigned)_hitOverflow);

    if (_hitCount == 0) {
        CUS_DBGLN("[NPK][MATRIX][SUMMARY] No complete response/evidence found. Sensor/config/bus is still unresolved.");
        return;
    }

    CUS_DBGLN("[NPK][MATRIX][SUMMARY] Every hit is traceable by CASE; SUCCESS_VALID_FRAME is the strongest match.");
    for (uint8_t i = 0; i < _hitCount; ++i) {
        const MatrixHit &hit = _hits[i];
        CUS_DBGF("[NPK][MATRIX][HIT] case=%03u stage=%s profile=%s baud=%lu format=%s slave=%u func=0x%02X start=0x%04X qty=%u map=%s class=%s status=0x%02X\n",
                 (unsigned)hit.caseNumber,
                 hit.stage,
                 TRANSPORTS[hit.transportIndex].name,
                 (unsigned long)TRANSPORTS[hit.transportIndex].baud,
                 TRANSPORTS[hit.transportIndex].format,
                 (unsigned)hit.slaveId,
                 (unsigned)hit.functionCode,
                 (unsigned)hit.startAddress,
                 (unsigned)hit.quantity,
                 hit.mapName,
                 statusClass(hit.status),
                 (unsigned)hit.status);
    }
}

void NpkMatrixTest::restoreConfiguredTransport() {
    activateTransport(0);
    CUS_DBGLN("[NPK][MATRIX] Configured UART profile restored; MyNPK is rebound by the main harness.");
}

void NpkMatrixTest::run() {
    resetState();

    CUS_DBGLN("\n[NPK][MATRIX] ===== START READ-ONLY PARAMETER MATRIX =====");
    CUS_DBGF("[NPK][MATRIX] Horizontal: fixed configured profile %lu 8N1 with slave=1 and legacy block.\n",
             (unsigned long)NPK_BAUDRATE);
    for (uint8_t transportIndex = 0; transportIndex < MATRIX_TRANSPORT_COUNT; ++transportIndex) {
        (void)runCase("HORIZONTAL_BAUD", transportIndex, NPK_MODBUS_SLAVE_ID, MAP_CANDIDATES[0]);
    }

    CUS_DBGLN("[NPK][MATRIX] Vertical map expansion: each soil attribute independently at slave=1 using FC03.");
    for (uint8_t transportIndex = 0; transportIndex < MATRIX_TRANSPORT_COUNT; ++transportIndex) {
        for (uint8_t mapIndex = 1; mapIndex < MATRIX_MAP_COUNT; ++mapIndex) {
            (void)runCase("VERTICAL_MAP", transportIndex, NPK_MODBUS_SLAVE_ID, MAP_CANDIDATES[mapIndex]);
        }
    }

    if (_targetCount == 0) {
        CUS_DBGLN("[NPK][MATRIX] No FC03 response evidence; testing each attribute with FC04 at slave=1.");
        for (uint8_t transportIndex = 0; transportIndex < MATRIX_TRANSPORT_COUNT; ++transportIndex) {
            for (uint8_t mapIndex = 0; mapIndex < MATRIX_MAP_COUNT; ++mapIndex) {
                MatrixMap inputMap = MAP_CANDIDATES[mapIndex];
                inputMap.functionCode = 0x04;
                (void)runCase("VERTICAL_MAP_FC04",
                              transportIndex,
                              NPK_MODBUS_SLAVE_ID,
                              inputMap);
            }
        }
    }

    if (_targetCount == 0) {
        CUS_DBGLN("[NPK][MATRIX] No response evidence; expanding slave IDs with FC03.");
        const MatrixMap idProbe = {"id_probe_holding", 0x03, 0x0000, 1U, "raw=probe"};
        for (uint8_t transportIndex = 0;
             transportIndex < MATRIX_TRANSPORT_COUNT && _targetCount == 0;
             ++transportIndex) {
             for (uint8_t slaveId = NPK_MODBUS_SLAVE_ID;
                 slaveId <= MATRIX_MAX_SLAVE_ID && _targetCount == 0;
                 ++slaveId) {
                (void)runCase("VERTICAL_SLAVE_FC03", transportIndex, slaveId, idProbe);
            }
        }
    }

    if (_targetCount == 0) {
        CUS_DBGLN("[NPK][MATRIX] Still no response evidence; expanding slave IDs with FC04.");
        const MatrixMap idProbe = {"id_probe_input", 0x04, 0x0000, 1U, "raw=probe"};
        for (uint8_t transportIndex = 0;
             transportIndex < MATRIX_TRANSPORT_COUNT && _targetCount == 0;
             ++transportIndex) {
             for (uint8_t slaveId = NPK_MODBUS_SLAVE_ID;
                 slaveId <= MATRIX_MAX_SLAVE_ID && _targetCount == 0;
                 ++slaveId) {
                (void)runCase("VERTICAL_SLAVE_FC04", transportIndex, slaveId, idProbe);
            }
        }
    }

    if (_targetCount > 0) {
        CUS_DBGLN("[NPK][MATRIX] Confirming all candidate maps for each transport/slave target.");
        for (uint8_t targetIndex = 0; targetIndex < _targetCount; ++targetIndex) {
            const MatrixTarget &target = _targets[targetIndex];
            for (uint8_t mapIndex = 0; mapIndex < MATRIX_MAP_COUNT; ++mapIndex) {
                (void)runCase("CONFIRM_MAP",
                               target.transportIndex,
                               target.slaveId,
                               MAP_CANDIDATES[mapIndex]);
            }

            CUS_DBGLN("[NPK][MATRIX] Confirming FC04 candidate maps for each discovered target.");
            for (uint8_t mapIndex = 0; mapIndex < MATRIX_MAP_COUNT; ++mapIndex) {
                MatrixMap inputMap = MAP_CANDIDATES[mapIndex];
                inputMap.functionCode = 0x04;
                (void)runCase("CONFIRM_MAP_FC04",
                              target.transportIndex,
                              target.slaveId,
                              inputMap);
            }
        }
    }

    printSummary();
    restoreConfiguredTransport();
    CUS_DBGLN("[NPK][MATRIX] ===== END READ-ONLY PARAMETER MATRIX =====");
}
