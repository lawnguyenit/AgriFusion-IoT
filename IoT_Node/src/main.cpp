#include <Arduino.h>

#include "Config.h"
#include "Sht30Probe.h"

/* Normal production entry point, kept here for quick restoration after testing:
#include "AppEntry.h"

void setup() {
    appEntrySetup();
}

void loop() {
    appEntryLoop();
}
*/

void setup() {
#if DEBUG_MODE
    DEBUG_PORT.begin(DEBUG_BAUDRATE);
    delay(300);
#endif
    sht30ProbeBegin();
}

void loop() {
    sht30ProbeLoop();
    delay(50);
}
