#ifndef OTA_STATE_STORE_H
#define OTA_STATE_STORE_H

#include <Arduino.h>

struct OtaPendingValidationInfo {
    bool active = false;
    String requestId;
    String targetVersion;
    String targetPartition;
    String previousPartition;
    uint32_t bootCount = 0;
};

struct OtaStoredEvent {
    bool valid = false;
    String stage;
    String status;
    String detail;
    String version;
    String requestId;
};

class OtaStateStore {
public:
    bool savePendingValidation(const OtaPendingValidationInfo &info);
    bool loadPendingValidation(OtaPendingValidationInfo &info);
    bool incrementPendingValidationBootCount(uint32_t &newCount);
    bool clearPendingValidation();

    String loadLastHandledRequestId();
    bool saveLastHandledRequestId(const String &requestId);

    bool savePendingEvent(const OtaStoredEvent &event);
    bool loadPendingEvent(OtaStoredEvent &event);
    bool clearPendingEvent();
};

#endif
