#ifndef OTA_MANAGER_H
#define OTA_MANAGER_H

#include <Arduino.h>
#include <FirebaseESP32.h>

struct OtaCommand {
    bool enabled = false;
    bool force = false;
    String requestId;
    String version;
    String url;
    String md5;
};

class OtaManager {
public:
    bool fetchCommand(FirebaseData &fbdo, const char *basePath, OtaCommand &cmd, String &err);
    bool disableCommand(FirebaseData &fbdo, const char *basePath);

    bool performHttpOta(const OtaCommand &cmd, String &targetPartitionLabel, String &errorDetail);
};

#endif
