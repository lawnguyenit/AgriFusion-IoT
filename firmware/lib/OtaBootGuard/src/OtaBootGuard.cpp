#include "OtaBootGuard.h"

#include <Update.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>
#include <esp_system.h>

namespace {
OtaStoredEvent makeEvent(const char *stage, const char *status, const String &detail, const String &version, const String &requestId) {
    OtaStoredEvent ev;
    ev.valid = true;
    ev.stage = stage;
    ev.status = status;
    ev.detail = detail;
    ev.version = version;
    ev.requestId = requestId;
    return ev;
}
}  // namespace

void OtaBootGuard::begin(OtaStateStore &store, uint32_t maxPendingBoots) {
    _info = OtaBootGuardInfo{};
    _info.runningVersion = currentRunningVersion();
    _info.runningPartition = currentRunningPartition();
    _info.resetReason = static_cast<int>(esp_reset_reason());

    OtaPendingValidationInfo pending;
    if (!store.loadPendingValidation(pending) || !pending.active) {
        return;
    }

    _info.pendingValidationObserved = true;
    _info.targetPartition = pending.targetPartition;
    _info.previousPartition = pending.previousPartition;
    _info.requestId = pending.requestId;

    if (pending.targetPartition.length() && _info.runningPartition != pending.targetPartition) {
        _info.detail = "pending target mismatch after reboot";
        store.savePendingEvent(makeEvent("boot", "failed", _info.detail, _info.runningVersion, pending.requestId));
        store.clearPendingValidation();
        return;
    }

    uint32_t bootCount = pending.bootCount;
    if (store.incrementPendingValidationBootCount(bootCount)) {
        _info.pendingBootCount = bootCount;
    } else {
        _info.pendingBootCount = pending.bootCount + 1;
    }

    _info.detail = "pending validation boot";
    store.savePendingEvent(makeEvent("boot", "pending_validation", _info.detail, _info.runningVersion, pending.requestId));

    if (_info.pendingBootCount <= maxPendingBoots) {
        return;
    }

    _info.rollbackTriggered = true;
    _info.detail = "too many pending-validation boots -> rollback";
    store.savePendingEvent(makeEvent("rollback", "scheduled", _info.detail, _info.runningVersion, pending.requestId));

    bool rollbackOk = false;
    if (pending.previousPartition.length() > 0) {
        const esp_partition_t *prev = esp_partition_find_first(
            ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_ANY, pending.previousPartition.c_str());
        if (prev) {
            rollbackOk = (esp_ota_set_boot_partition(prev) == ESP_OK);
        }
    }

    // Fallback for 2-slot OTA when previous label was not found.
    if (!rollbackOk) {
        rollbackOk = Update.canRollBack() && Update.rollBack();
    }

    if (rollbackOk) {
        store.clearPendingValidation();
        ESP.restart();
    } else {
        store.savePendingEvent(makeEvent("rollback", "failed", "cannot set boot partition", _info.runningVersion, pending.requestId));
    }
}

bool OtaBootGuard::confirmPendingValidation(OtaStateStore &store) {
    OtaPendingValidationInfo pending;
    if (!store.loadPendingValidation(pending) || !pending.active) {
        return false;
    }

    store.clearPendingValidation();
    store.savePendingEvent(makeEvent("validation", "success", "firmware confirmed healthy", currentRunningVersion(), pending.requestId));
    return true;
}

bool OtaBootGuard::isPendingValidation() const {
    return _info.pendingValidationObserved && !_info.rollbackTriggered;
}

const OtaBootGuardInfo &OtaBootGuard::info() const {
    return _info;
}

String OtaBootGuard::currentRunningVersion() {
    const esp_app_desc_t *desc = esp_ota_get_app_description();
    if (!desc) {
        return "unknown";
    }
    return String(desc->version);
}

String OtaBootGuard::currentRunningPartition() {
    const esp_partition_t *running = esp_ota_get_running_partition();
    if (!running || !running->label) {
        return "unknown";
    }
    return String(running->label);
}
