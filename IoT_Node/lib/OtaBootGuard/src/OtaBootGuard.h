#ifndef OTA_BOOT_GUARD_H
#define OTA_BOOT_GUARD_H

#include <Arduino.h>

#include "OtaStateStore.h"

struct OtaBootGuardInfo {
    bool pendingValidationObserved = false;
    bool rollbackTriggered = false;
    String detail;
    String runningVersion;
    String runningPartition;
    String targetPartition;
    String previousPartition;
    String requestId;
    uint32_t pendingBootCount = 0;
    int resetReason = 0;
};

class OtaBootGuard {
public:
    void begin(OtaStateStore &store, uint32_t maxPendingBoots);
    bool confirmPendingValidation(OtaStateStore &store);

    bool isPendingValidation() const;
    const OtaBootGuardInfo &info() const;

    static String currentRunningVersion();
    static String currentRunningPartition();

private:
    OtaBootGuardInfo _info;
};

#endif
