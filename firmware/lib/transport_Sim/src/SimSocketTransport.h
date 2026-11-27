#ifndef SIM_SOCKET_TRANSPORT_H
#define SIM_SOCKET_TRANSPORT_H

#include <Arduino.h>

struct RawSimSocketOpenResult {
    bool netOpenOk = false;
    bool socketOpenOk = false;
    int cipOpenCode = -1;
    String detail;
    String netOpenResponse;
    String openResponse;
    String closeResponse;
};

struct RawSimSocketSendResult {
    bool promptOk = false;
    bool sendOk = false;
    String mode;
    String detail;
    String promptResponse;
    String sendResponse;
};

struct RawSimSocketReadResult {
    bool ok = false;
    size_t availableBytes = 0;
    String detail;
    String availableResponse;
    String readResponse;
    String payload;
};

struct RawSimSocketTransactionConfig {
    const char *host = nullptr;
    uint16_t port = 0;
    String payload;
    uint8_t socketId = 0;
    uint32_t timeoutMs = 5000;
    uint32_t retries = 1;
    size_t readChunkBytes = 512;
    size_t maxPayloadBytes = 1024;
    uint32_t idleReadWindowMs = 800;
    bool useLenMode = true;
    bool enableManualRx = true;
};

struct RawSimSocketTransactionResult {
    bool netOpenOk = false;
    bool socketOpenOk = false;
    bool sendOk = false;
    bool rxModeOk = false;
    bool payloadOk = false;
    int cipOpenCode = -1;
    size_t availableBytes = 0;
    size_t payloadBytes = 0;
    String stage;
    String detail;
    String netOpenResponse;
    String openResponse;
    String promptResponse;
    String sendResponse;
    String availableResponse;
    String readResponse;
    String closeResponse;
    String payload;
};

struct RawSimHttpProbeResult {
    bool netOpenOk = false;
    bool socketOpenOk = false;
    bool sendOk = false;
    bool readOk = false;
    bool headerOk = false;
    int cipOpenCode = -1;
    size_t availableBytes = 0;
    String stage;
    String detail;
    String netOpenResponse;
    String openResponse;
    String promptResponse;
    String sendResponse;
    String availableResponse;
    String readResponse;
    String closeResponse;
    String header;
};

bool openRawSimTcpSocket(const char *host,
                         uint16_t port,
                         uint32_t timeoutMs,
                         RawSimSocketOpenResult &result,
                         uint8_t socketId = 0);

bool sendRawSimSocketLenMode(uint8_t socketId,
                             const String &payload,
                             uint32_t timeoutMs,
                             RawSimSocketSendResult &result);

bool sendRawSimSocketCtrlZMode(uint8_t socketId,
                               const String &payload,
                               uint32_t timeoutMs,
                               RawSimSocketSendResult &result);

bool enableRawSimManualReceive(String &response);

bool pollRawSimSocketAvailable(uint8_t socketId,
                               uint32_t timeoutMs,
                               RawSimSocketReadResult &result);

bool readRawSimSocket(uint8_t socketId,
                      size_t maxBytes,
                      uint32_t timeoutMs,
                      RawSimSocketReadResult &result);

bool closeRawSimSocket(uint8_t socketId, String &response);

RawSimSocketTransactionResult runRawSimSocketTransaction(const RawSimSocketTransactionConfig &config);

RawSimHttpProbeResult runRawSimHttpProbe(const char *host,
                                         uint16_t port,
                                         const char *path = "/",
                                         const char *hostHeader = nullptr,
                                         uint32_t timeoutMs = 5000);

#endif
