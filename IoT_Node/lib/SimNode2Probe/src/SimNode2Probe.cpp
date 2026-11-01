#include "SimNode2Probe.h"

#include <Arduino.h>

#include "Config.h"
#include "RtdbRestClient.h"
#include "SimA7680C.h"
#include "TransportStability.h"

namespace {

constexpr uint32_t RETRY_INTERVAL_MS = 5000UL;

bool gWriteSucceeded = false;
uint32_t gAttemptNumber = 0;
uint32_t gNextAttemptAtMs = 0;

bool runTestAttempt(bool waitForBootSettle) {
    ++gAttemptNumber;
    CUS_DBGF("\n=== SIM TO NODE2 DEBUG WRITE TEST attempt=%lu ===\n",
             static_cast<unsigned long>(gAttemptNumber));
    CUS_DBGF("[SIM][RTDB_TEST] target=%s value_format=uptime_seconds retry_ms=%lu\n",
             APP_RTDB_PATH_NODE_TELEMETRY_PROBE,
             static_cast<unsigned long>(RETRY_INTERVAL_MS));

    const bool simSetupOk = setupSIM(waitForBootSettle);
    CUS_DBGF("[SIM][RTDB_TEST] setupSIM=%d\n", simSetupOk ? 1 : 0);
    if (!simSetupOk) {
        CUS_DBGLN("[SIM][RTDB_TEST] skipped reason=sim_setup_failed");
        return false;
    }

    const CloudTransportReport transport = runCloudTransportCycle();
    printCloudTransportReport(transport);
    if (!transport.transportUsable) {
        CUS_DBGF("[SIM][RTDB_TEST] skipped reason=transport_not_usable stage=%s\n",
                 transport.stage.c_str());
        return false;
    }

    RtdbRestClient &client = rtdbRestClient();
    if (!client.configured()) {
        CUS_DBGLN("[SIM][RTDB_TEST] skipped reason=rtdb_client_not_configured");
        return false;
    }

    const String value(static_cast<unsigned long>(millis() / 1000UL));
    RtdbRestResponse response;
    const bool writeOk = client.putRawJson(APP_RTDB_PATH_NODE_TELEMETRY_PROBE,
                                           value,
                                           response,
                                           true);
    CUS_DBGF("[SIM][RTDB_TEST] ok=%d path=%s value=%s http=%d stage=%s transport=%d response=%d detail=%s\n",
             writeOk ? 1 : 0,
             APP_RTDB_PATH_NODE_TELEMETRY_PROBE,
             value.c_str(),
             response.statusCode,
             response.stage.c_str(),
             response.transportOk ? 1 : 0,
             response.responseReceived ? 1 : 0,
             response.detail.c_str());
    return writeOk;
}

}  // namespace

void simNode2ProbeBegin() {
    CUS_DBGLN("\n=== SIM TO NODE2 DEBUG WRITE TEST; retry every 5s until success ===");
    gWriteSucceeded = runTestAttempt(true);
    if (gWriteSucceeded) {
        CUS_DBGLN("[SIM][RTDB_TEST] complete; successful write, retry stopped");
        return;
    }

    gNextAttemptAtMs = millis() + RETRY_INTERVAL_MS;
    CUS_DBGF("[SIM][RTDB_TEST] next_attempt_in_ms=%lu\n",
             static_cast<unsigned long>(RETRY_INTERVAL_MS));
}

void simNode2ProbeLoop() {
    if (gWriteSucceeded) {
        delay(1000);
        return;
    }

    if (static_cast<int32_t>(millis() - gNextAttemptAtMs) < 0) {
        delay(100);
        return;
    }

    gWriteSucceeded = runTestAttempt(false);
    if (gWriteSucceeded) {
        CUS_DBGLN("[SIM][RTDB_TEST] complete; successful write, retry stopped");
        return;
    }

    gNextAttemptAtMs = millis() + RETRY_INTERVAL_MS;
    CUS_DBGF("[SIM][RTDB_TEST] next_attempt_in_ms=%lu\n",
             static_cast<unsigned long>(RETRY_INTERVAL_MS));
}
