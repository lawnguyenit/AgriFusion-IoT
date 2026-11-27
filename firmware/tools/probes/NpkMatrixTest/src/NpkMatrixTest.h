#ifndef NPK_MATRIX_TEST_H
#define NPK_MATRIX_TEST_H

#include <Arduino.h>

class HardwareSerial;

class NpkMatrixTest {
public:
    explicit NpkMatrixTest(HardwareSerial &serial);

    // Runs only read-only Modbus transactions and restores the configured
    // UART profile before returning.
    void run();

private:
    static constexpr uint8_t MATRIX_TRANSPORT_COUNT = 1U;
    static constexpr uint8_t MATRIX_MAP_COUNT = 15U;
    static constexpr uint8_t MATRIX_MAX_SLAVE_ID = 10U;
    static constexpr uint8_t MATRIX_MAX_TARGETS = 8U;
    static constexpr uint8_t MATRIX_MAX_HITS = 128U;

    struct MatrixTransport {
        const char *name;
        uint32_t baud;
        uint32_t serialConfig;
        const char *format;
    };

    struct MatrixMap {
        const char *name;
        uint8_t functionCode;
        uint16_t startAddress;
        uint8_t quantity;
        const char *decodeHint;
    };

    struct MatrixTarget {
        uint8_t transportIndex;
        uint8_t slaveId;
    };

    struct MatrixHit {
        uint16_t caseNumber;
        uint8_t transportIndex;
        uint8_t slaveId;
        uint8_t functionCode;
        uint16_t startAddress;
        uint8_t quantity;
        uint8_t status;
        const char *stage;
        const char *mapName;
    };

    HardwareSerial &_serial;
    const MatrixTransport *_activeTransport = nullptr;

    MatrixTarget _targets[MATRIX_MAX_TARGETS] = {};
    MatrixHit _hits[MATRIX_MAX_HITS] = {};
    uint8_t _targetCount = 0;
    uint8_t _hitCount = 0;
    uint16_t _hitOverflow = 0;
    uint16_t _caseCount = 0;
    uint16_t _successCount = 0;
    uint16_t _exceptionCount = 0;
    uint16_t _frameErrorCount = 0;
    uint16_t _timeoutCount = 0;

    static const MatrixTransport TRANSPORTS[MATRIX_TRANSPORT_COUNT];
    static const MatrixMap MAP_CANDIDATES[MATRIX_MAP_COUNT];

    void activateTransport(uint8_t transportIndex);
    void flushSerial();
    uint8_t runCase(const char *stage,
                    uint8_t transportIndex,
                    uint8_t slaveId,
                    const MatrixMap &map);
    void rememberTarget(uint8_t transportIndex, uint8_t slaveId);
    void rememberHit(uint16_t caseNumber,
                     uint8_t transportIndex,
                     uint8_t slaveId,
                     const MatrixMap &map,
                     uint8_t status,
                     const char *stage);
    void resetState();
    void printSummary();
    void restoreConfiguredTransport();

    static const char *statusClass(uint8_t status);
    static bool hasBusEvidence(uint8_t status);
};

#endif
