#include "TransportStability.h"

#include "Config.h"
#include "DateTime.h"
#include "SimHttpClient.h"

namespace {
String firstHeaderLine(const String &header) {
    int end = header.indexOf('\n');
    String line = end >= 0 ? header.substring(0, end) : header;
    line.trim();
    return line;
}

String dateHeaderLine(const String &header) {
    int start = header.indexOf("Date:");
    if (start < 0) {
        return "";
    }
    int end = header.indexOf('\n', start);
    String line = end >= 0 ? header.substring(start, end) : header.substring(start);
    line.trim();
    return line;
}

void applyTimeBootstrap(TransportCycleReport &report) {
    report.timeWasSaneBefore = timeLooksSane();
    report.timeBefore = getCurrentTimeStr();
    report.simClockRaw = simReadNetworkTimeRaw();

    if (report.timeWasSaneBefore) {
        report.timeAfter = report.timeBefore;
        return;
    }

    report.timeSyncFromSimOk = syncTimeFromSIM();
    if (!report.timeSyncFromSimOk && report.primaryProbe.headerOk) {
        report.timeSyncFromHttpOk = syncTimeFromHttpHeader(report.primaryProbe.header);
    }

    report.timeAfter = getCurrentTimeStr();
}

void logPrimaryHttpProbe(const RawSimHttpProbeResult &probe) {
    CUS_DBGF("[RAW][PRIMARY] http_ok=%d stage=%s detail=%s code=%d\n",
             probe.headerOk ? 1 : 0,
             probe.stage.c_str(),
             probe.detail.c_str(),
             probe.cipOpenCode);
    CUS_DBGF("[RAW][PRIMARY] netopen={%s}\n", probe.netOpenResponse.c_str());
    CUS_DBGF("[RAW][PRIMARY] open={%s}\n", probe.openResponse.c_str());
    CUS_DBGF("[RAW][PRIMARY] prompt={%s}\n", probe.promptResponse.c_str());
    CUS_DBGF("[RAW][PRIMARY] send={%s}\n", probe.sendResponse.c_str());
    CUS_DBGF("[RAW][PRIMARY] available={%s}\n", probe.availableResponse.c_str());
    CUS_DBGF("[RAW][PRIMARY] read={%s}\n", probe.readResponse.c_str());
    CUS_DBGF("[RAW][PRIMARY] close={%s}\n", probe.closeResponse.c_str());
    if (probe.headerOk) {
        CUS_DBGF("[RAW][PRIMARY] status=%s\n", firstHeaderLine(probe.header).c_str());
        CUS_DBGF("[RAW][PRIMARY] date=%s\n", dateHeaderLine(probe.header).c_str());
    }
}

HttpTransportProbeReport runModemHttpTransportProbe() {
    HttpTransportProbeReport report;

    SimHttpClient http;
    SimHttpRequest request;
    request.method = SimHttpMethod::Get;
    request.url = APP_SIM_HTTP_PROBE_URL;
    request.readHeader = true;
    request.readBody = false;
    request.actionTimeoutMs = 30000;

    SimHttpResponse response;
    report.ok = http.perform(request, response);
    report.statusCode = response.statusCode;
    report.stage = response.stage;
    report.detail = response.detail;
    report.header = response.header;
    return report;
}

void applyCloudTimeBootstrap(CloudTransportReport &report) {
    report.timeWasSaneBefore = timeLooksSane();
    report.timeBefore = getCurrentTimeStr();
    report.simClockRaw = simReadNetworkTimeRaw();

    if (report.timeWasSaneBefore) {
        report.timeAfter = report.timeBefore;
        report.timeReadyAfter = true;
        return;
    }

    report.timeSyncFromSimOk = syncTimeFromSIM();
    if (!report.timeSyncFromSimOk && report.httpProbe.header.length()) {
        report.timeSyncFromHttpOk = syncTimeFromHttpHeader(report.httpProbe.header);
    }

    report.timeAfter = getCurrentTimeStr();
    report.timeReadyAfter = timeLooksSane();
}
}  // namespace

TransportCycleReport runTransportCycle() {
    TransportCycleReport report;
    report.primaryProbe = runRawSimHttpProbe(SIM_TEST_DNS_HOST,
                                             SIM_TEST_DNS_PORT,
                                             "/",
                                             SIM_TEST_DNS_HOST,
                                             SIM_TEST_SOCKET_TIMEOUT_MS);
    applyTimeBootstrap(report);
    report.connectivity = runSimConnectivityProbe(true, &report.primaryProbe);
    return report;
}

void printTransportCycleReport(const TransportCycleReport &report) {
    CUS_DBGF("[TIME] sane_before=%d sim_sync=%d http_sync=%d now_before=%s now_after=%s cclk=%s\n",
             report.timeWasSaneBefore ? 1 : 0,
             report.timeSyncFromSimOk ? 1 : 0,
             report.timeSyncFromHttpOk ? 1 : 0,
             report.timeBefore.c_str(),
             report.timeAfter.c_str(),
             report.simClockRaw.c_str());

    printSimConnectivityReport(report.connectivity);
    if (SIM_ENABLE_FORENSIC_DUMP && report.connectivity.uartReady && !report.connectivity.rawHttpOk) {
        printSimForensicAtSnapshot();
    }
#if SIM_VERBOSE_PROBE_DETAIL
    logPrimaryHttpProbe(report.primaryProbe);
#endif
}

CloudTransportReport runCloudTransportCycle() {
    CloudTransportReport report;
    report.network = simReadNetworkState(true);

    if (report.network.gprsConnected) {
        report.httpProbe = runModemHttpTransportProbe();
    } else {
        report.httpProbe.stage = "http_probe_skipped";
        report.httpProbe.detail = "packet_session_not_ready";
    }

    applyCloudTimeBootstrap(report);

    if (!report.network.simReady) {
        report.stage = "sim_not_ready";
        report.detail = "CPIN not ready";
        return report;
    }
    if (!report.network.networkRegistered) {
        report.stage = "network_not_registered";
        report.detail = "CREG/CGREG/CEREG not registered";
        return report;
    }
    if (!report.network.packetAttached) {
        report.stage = "packet_not_attached";
        report.detail = "CGATT not attached";
        return report;
    }
    if (!report.network.gprsConnected) {
        report.stage = "gprs_not_connected";
        report.detail = "CGACT indicates packet session not usable";
        return report;
    }

    report.transportUsable = report.httpProbe.ok;
    if (report.transportUsable) {
        report.stage = report.timeReadyAfter ? "cloud_transport_ready" : "cloud_transport_ready_time_pending";
        report.detail = String("http=") + report.httpProbe.stage + " | " + report.httpProbe.detail;
    } else {
        report.stage = "http_transport_fail";
        report.detail = report.httpProbe.stage + " | " + report.httpProbe.detail;
    }

    return report;
}

void printCloudTransportReport(const CloudTransportReport &report) {
    CUS_DBGF("[TIME] sane_before=%d sim_sync=%d http_sync=%d time_ready=%d now_before=%s now_after=%s cclk=%s\n",
             report.timeWasSaneBefore ? 1 : 0,
             report.timeSyncFromSimOk ? 1 : 0,
             report.timeSyncFromHttpOk ? 1 : 0,
             report.timeReadyAfter ? 1 : 0,
             report.timeBefore.c_str(),
             report.timeAfter.c_str(),
             report.simClockRaw.c_str());

    CUS_DBGF("[SIM][CLOUD] stage=%s detail=%s sim=%d reg=%d attach=%d gprs=%d ip=%s csq=%d dbm=%d op=%s\n",
             report.stage.c_str(),
             report.detail.c_str(),
             report.network.simReady ? 1 : 0,
             report.network.networkRegistered ? 1 : 0,
             report.network.packetAttached ? 1 : 0,
             report.network.gprsConnected ? 1 : 0,
             report.network.localIp.c_str(),
             report.network.signalDbm != 0 ? ((report.network.signalDbm + 113) / 2) : 0,
             report.network.signalDbm,
             report.network.operatorName.c_str());

    CUS_DBGF("[SIM][HTTP] ok=%d status=%d stage=%s detail=%s\n",
             report.httpProbe.ok ? 1 : 0,
             report.httpProbe.statusCode,
             report.httpProbe.stage.c_str(),
             report.httpProbe.detail.c_str());

    if (report.httpProbe.header.length()) {
        CUS_DBGF("[SIM][HTTP] status=%s\n", firstHeaderLine(report.httpProbe.header).c_str());
        CUS_DBGF("[SIM][HTTP] date=%s\n", dateHeaderLine(report.httpProbe.header).c_str());
    }

    if (SIM_ENABLE_FORENSIC_DUMP && report.network.simReady && report.network.gprsConnected && !report.transportUsable) {
        printSimForensicAtSnapshot();
    }
}
