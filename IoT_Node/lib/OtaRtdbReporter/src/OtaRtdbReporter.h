#ifndef OTA_RTDB_REPORTER_H
#define OTA_RTDB_REPORTER_H

#include <Arduino.h>
#include <FirebaseESP32.h>

#include "OtaStateStore.h"

class OtaRtdbReporter {
public:
    OtaRtdbReporter(const char *statusPath, const char *historyPath);

    bool reportEvent(FirebaseData &fbdo, const OtaStoredEvent &event,
                     const String &runningVersion, const String &runningPartition);

    bool reportStatus(FirebaseData &fbdo, const char *state, const char *detail,
                      const String &version, const String &requestId,
                      const String &runningPartition);

    bool flushPendingEvent(FirebaseData &fbdo, OtaStateStore &store,
                           const String &runningVersion, const String &runningPartition);

private:
    String _statusPath;
    String _historyPath;
};

#endif
