#include "OtaStateStore.h"

#include <Preferences.h>

namespace {
const char *kNs = "ota";

const char *kPvAct = "pv_act";
const char *kPvReq = "pv_req";
const char *kPvVer = "pv_ver";
const char *kPvTgt = "pv_tgt";
const char *kPvPrev = "pv_prev";
const char *kPvCnt = "pv_cnt";

const char *kLastReq = "last_req";

const char *kEvAct = "ev_act";
const char *kEvStage = "ev_stage";
const char *kEvStat = "ev_stat";
const char *kEvDet = "ev_det";
const char *kEvVer = "ev_ver";
const char *kEvReq = "ev_req";
}  // namespace

bool OtaStateStore::savePendingValidation(const OtaPendingValidationInfo &info) {
    Preferences prefs;
    if (!prefs.begin(kNs, false)) {
        return false;
    }
    prefs.putBool(kPvAct, info.active);
    prefs.putString(kPvReq, info.requestId);
    prefs.putString(kPvVer, info.targetVersion);
    prefs.putString(kPvTgt, info.targetPartition);
    prefs.putString(kPvPrev, info.previousPartition);
    prefs.putUInt(kPvCnt, info.bootCount);
    prefs.end();
    return true;
}

bool OtaStateStore::loadPendingValidation(OtaPendingValidationInfo &info) {
    Preferences prefs;
    if (!prefs.begin(kNs, false)) {
        return false;
    }
    info = OtaPendingValidationInfo{};
    if (prefs.isKey(kPvAct)) info.active = prefs.getBool(kPvAct, false);
    if (prefs.isKey(kPvReq)) info.requestId = prefs.getString(kPvReq, "");
    if (prefs.isKey(kPvVer)) info.targetVersion = prefs.getString(kPvVer, "");
    if (prefs.isKey(kPvTgt)) info.targetPartition = prefs.getString(kPvTgt, "");
    if (prefs.isKey(kPvPrev)) info.previousPartition = prefs.getString(kPvPrev, "");
    if (prefs.isKey(kPvCnt)) info.bootCount = prefs.getUInt(kPvCnt, 0);
    prefs.end();
    return true;
}

bool OtaStateStore::incrementPendingValidationBootCount(uint32_t &newCount) {
    Preferences prefs;
    if (!prefs.begin(kNs, false)) {
        return false;
    }
    uint32_t current = prefs.getUInt(kPvCnt, 0);
    current++;
    prefs.putUInt(kPvCnt, current);
    prefs.end();
    newCount = current;
    return true;
}

bool OtaStateStore::clearPendingValidation() {
    Preferences prefs;
    if (!prefs.begin(kNs, false)) {
        return false;
    }
    prefs.putBool(kPvAct, false);
    prefs.putString(kPvReq, "");
    prefs.putString(kPvVer, "");
    prefs.putString(kPvTgt, "");
    prefs.putString(kPvPrev, "");
    prefs.putUInt(kPvCnt, 0);
    prefs.end();
    return true;
}

String OtaStateStore::loadLastHandledRequestId() {
    Preferences prefs;
    if (!prefs.begin(kNs, false)) {
        return String();
    }
    String value;
    if (prefs.isKey(kLastReq)) {
        value = prefs.getString(kLastReq, "");
    }
    prefs.end();
    return value;
}

bool OtaStateStore::saveLastHandledRequestId(const String &requestId) {
    Preferences prefs;
    if (!prefs.begin(kNs, false)) {
        return false;
    }
    prefs.putString(kLastReq, requestId);
    prefs.end();
    return true;
}

bool OtaStateStore::savePendingEvent(const OtaStoredEvent &event) {
    Preferences prefs;
    if (!prefs.begin(kNs, false)) {
        return false;
    }
    prefs.putBool(kEvAct, event.valid);
    prefs.putString(kEvStage, event.stage);
    prefs.putString(kEvStat, event.status);
    prefs.putString(kEvDet, event.detail);
    prefs.putString(kEvVer, event.version);
    prefs.putString(kEvReq, event.requestId);
    prefs.end();
    return true;
}

bool OtaStateStore::loadPendingEvent(OtaStoredEvent &event) {
    Preferences prefs;
    if (!prefs.begin(kNs, false)) {
        return false;
    }
    event = OtaStoredEvent{};
    if (prefs.isKey(kEvAct)) event.valid = prefs.getBool(kEvAct, false);
    if (prefs.isKey(kEvStage)) event.stage = prefs.getString(kEvStage, "");
    if (prefs.isKey(kEvStat)) event.status = prefs.getString(kEvStat, "");
    if (prefs.isKey(kEvDet)) event.detail = prefs.getString(kEvDet, "");
    if (prefs.isKey(kEvVer)) event.version = prefs.getString(kEvVer, "");
    if (prefs.isKey(kEvReq)) event.requestId = prefs.getString(kEvReq, "");
    prefs.end();
    return true;
}

bool OtaStateStore::clearPendingEvent() {
    Preferences prefs;
    if (!prefs.begin(kNs, false)) {
        return false;
    }
    prefs.putBool(kEvAct, false);
    prefs.putString(kEvStage, "");
    prefs.putString(kEvStat, "");
    prefs.putString(kEvDet, "");
    prefs.putString(kEvVer, "");
    prefs.putString(kEvReq, "");
    prefs.end();
    return true;
}
