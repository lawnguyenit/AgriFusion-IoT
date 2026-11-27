#include "NetworkBridge.h"

#include "Config.h"

#if USE_SIM_NETWORK
#include "SimA7680C.h"
#else
#include <WiFi.h>
#include "WifiManager.h"
#endif

namespace {
bool gConnected = false;
}

bool networkSetup() {
#if USE_SIM_NETWORK
    gConnected = setupSIM();
#else
    gConnected = setupWifi();
#endif
    return gConnected;
}

void networkMaintain() {
#if USE_SIM_NETWORK
    static uint32_t lastCheckMs = 0;
    uint32_t intervalMs = gConnected ? SIM_NETWORK_CHECK_INTERVAL_MS : SIM_DEBUG_RECHECK_DELAY_MS;
    if (millis() - lastCheckMs < intervalMs) {
        return;
    }
    lastCheckMs = millis();
    gConnected = checkNetwork();
#else
    checkWifi();
    gConnected = (WiFi.status() == WL_CONNECTED);
#endif
}

bool networkIsConnected() {
    return gConnected;
}

int networkSignalDbm() {
#if USE_SIM_NETWORK
    return simSignalDbm();
#else
    return gConnected ? WiFi.RSSI() : 0;
#endif
}

String networkLocalIp() {
#if USE_SIM_NETWORK
    return simLocalIP();
#else
    return gConnected ? WiFi.localIP().toString() : String("0.0.0.0");
#endif
}

int networkStatusCode() {
#if USE_SIM_NETWORK
    return simStatusCode();
#else
    return (int)WiFi.status();
#endif
}

const char *networkTransportName() {
#if USE_SIM_NETWORK
    return "cellular";
#else
    return "wifi";
#endif
}
