#include "DeviceContext.h"

#include <esp_sleep.h>
#include <esp_system.h>

namespace {
String formatDeviceId() {
    uint64_t mac = ESP.getEfuseMac();
    char buf[32];
    snprintf(buf, sizeof(buf), "esp32s3-%04X%08X",
             (uint16_t)(mac >> 32), (uint32_t)mac);
    return String(buf);
}

String wakeReasonToString(esp_sleep_wakeup_cause_t cause) {
    switch (cause) {
        case ESP_SLEEP_WAKEUP_UNDEFINED: return "power_on_or_reset";
        case ESP_SLEEP_WAKEUP_EXT0: return "ext0";
        case ESP_SLEEP_WAKEUP_EXT1: return "ext1";
        case ESP_SLEEP_WAKEUP_TIMER: return "timer";
        case ESP_SLEEP_WAKEUP_TOUCHPAD: return "touchpad";
        case ESP_SLEEP_WAKEUP_ULP: return "ulp";
#if defined(ESP_SLEEP_WAKEUP_GPIO)
        case ESP_SLEEP_WAKEUP_GPIO: return "gpio";
#endif
        default: return "other";
    }
}
}  // namespace

void DeviceContext::begin() {
    if (_initialized) {
        return;
    }

    _deviceId = formatDeviceId();
    _resetReason = static_cast<int>(esp_reset_reason());
    _wakeReason = wakeReasonToString(esp_sleep_get_wakeup_cause());

    char bootBuf[64];
    uint32_t r = esp_random();
    snprintf(bootBuf, sizeof(bootBuf), "%s-%08lx", _deviceId.c_str(), (unsigned long)r);
    _bootId = bootBuf;

    _seq = 0;
    _initialized = true;
}

const String &DeviceContext::deviceId() const { return _deviceId; }
const String &DeviceContext::bootId() const { return _bootId; }
const String &DeviceContext::wakeReason() const { return _wakeReason; }
int DeviceContext::resetReason() const { return _resetReason; }

uint32_t DeviceContext::nextSeq() {
    _seq++;
    return _seq;
}

uint32_t DeviceContext::currentSeq() const { return _seq; }

