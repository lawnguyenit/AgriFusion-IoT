#include "WifiManager.h"
#include "Config.h"

static int wifiRetryCount = 0;
static const int WIFI_MAX_RETRY = 5;
static const uint32_t WIFI_RECONNECT_INTERVAL_MS = 5000;
static const uint32_t WIFI_RECONNECT_WAIT_MS = 1200;
static uint32_t lastReconnectAttemptMs = 0;

bool setupWifi() {
    CUS_DBGLN("\n[WIFI] --- BAT DAU KHOI DONG ---");
    CUS_DBGF("[WIFI] Dang ket noi vao: %s\n", WIFI_SSID);

    WiFi.mode(WIFI_STA);
    WiFi.persistent(false);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long startAttemptTime = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < WIFI_TIMEOUT_MS) {
        CUS_DBG(".");
        delay(250);
    }

    if (WiFi.status() == WL_CONNECTED) {
        CUS_DBGLN("\n[WIFI] -> Ket noi THANH CONG!");
        wifiRetryCount = 0;
        printWifiInfo();
        return true;
    }

    CUS_DBGLN("\n[WIFI] -> LOI: Ket noi THAT BAI (Qua thoi gian cho)\n");
    return false;
}

void checkWifi() {
    if (WiFi.status() == WL_CONNECTED) {
        wifiRetryCount = 0;
        return;
    }

    uint32_t now = millis();
    if (now - lastReconnectAttemptMs < WIFI_RECONNECT_INTERVAL_MS) {
        return;
    }
    lastReconnectAttemptMs = now;

    if (wifiRetryCount >= WIFI_MAX_RETRY) {
        CUS_DBGLN("[WIFI] Reset lai stack WiFi sau nhieu lan that bai.");
        WiFi.disconnect(true, true);
        delay(100);
        WiFi.mode(WIFI_OFF);
        delay(100);
        WiFi.mode(WIFI_STA);
        WiFi.setAutoReconnect(true);
        wifiRetryCount = 0;
    }

    wifiRetryCount++;
    CUS_DBGF("[WIFI] Dang thu ket noi lai... (%d/%d)\n", wifiRetryCount, WIFI_MAX_RETRY);

    wl_status_t st = WiFi.status();
    if (st == WL_NO_SSID_AVAIL || st == WL_CONNECT_FAILED || st == WL_DISCONNECTED) {
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    } else {
        WiFi.reconnect();
    }

    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_RECONNECT_WAIT_MS) {
        delay(100);
    }

    if (WiFi.status() == WL_CONNECTED) {
        CUS_DBGLN("[WIFI] Da khoi phuc ket noi!");
        wifiRetryCount = 0;
        printWifiInfo();
    }
}

void printWifiInfo() {
    Serial.println("=== THONG TIN WIFI ===");
    Serial.print("SSID: ");
    Serial.println(WiFi.SSID());
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("MAC Address: ");
    Serial.println(WiFi.macAddress());
    Serial.print("Signal (RSSI): ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    Serial.println("======================");
}
