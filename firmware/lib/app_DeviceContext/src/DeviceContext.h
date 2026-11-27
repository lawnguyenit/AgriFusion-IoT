#ifndef DEVICE_CONTEXT_H
#define DEVICE_CONTEXT_H

#include <Arduino.h>

class DeviceContext {
public:
    void begin();

    const String &deviceId() const;
    const String &bootId() const;
    const String &wakeReason() const;

    int resetReason() const;

    uint32_t nextSeq();
    uint32_t currentSeq() const;

private:
    bool _initialized = false;
    String _deviceId;
    String _bootId;
    String _wakeReason;
    int _resetReason = 0;
    uint32_t _seq = 0;
};

#endif
