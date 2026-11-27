#ifndef WAKE_CYCLE_H
#define WAKE_CYCLE_H

#include <Arduino.h>

// Results passed between the three explicit phases of one wake session.
// The structs contain observations only; phase policy stays in AppRuntime.
struct OpeningResult {
    bool storageReady = false;
    bool npkPrepared = false;
    bool sht30Ready = false;
    bool ds18b20Ready = false;
    bool soilMoistureReady = false;
    bool networkReady = false;
    bool cloudReady = false;
    bool timeReady = false;
    bool offlineReplayPending = false;
    String detail;
};

struct CollectionResult {
    bool ok = false;
    bool sensorAlarm = false;
    uint32_t elapsedMs = 0;
    String payload;
    String detail;
};

struct FinalizationResult {
    bool cloudReady = false;
    bool uploaded = false;
    bool buffered = false;
    bool sleepRequested = false;
    uint32_t sleepMs = 0;
    String reason;
    String stage;
    String detail;
};

#endif
