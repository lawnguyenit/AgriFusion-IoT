#include <Arduino.h>

#include "AppRuntime.h"
#include "Config.h"

namespace {
    AppRuntime gAppRuntime;
}

void setup() {
#if DEBUG_MODE
    DEBUG_PORT.begin(DEBUG_BAUDRATE);
    Serial.begin(DEBUG_BAUDRATE);
    delay(1000);
#endif

    gAppRuntime.begin();
}

void loop() {
    vTaskDelete(NULL);
}
