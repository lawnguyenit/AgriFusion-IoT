#ifndef TRANSPORT_STABILITY_H
#define TRANSPORT_STABILITY_H

#include <Arduino.h>

#include "SimA7680C.h"
#include "SimSocketTransport.h"

struct HttpTransportProbeReport {
    bool ok = false;
    int statusCode = -1;
    String stage;
    String detail;
    String header;
};

struct TransportCycleReport {
    RawSimHttpProbeResult primaryProbe;
    SimConnectivityReport connectivity;
    bool timeWasSaneBefore = false;
    bool timeSyncFromSimOk = false;
    bool timeSyncFromHttpOk = false;
    String timeBefore;
    String timeAfter;
    String simClockRaw;
};

struct CloudTransportReport {
    SimNetworkState network;
    HttpTransportProbeReport httpProbe;
    bool timeWasSaneBefore = false;
    bool timeSyncFromSimOk = false;
    bool timeSyncFromHttpOk = false;
    bool timeReadyAfter = false;
    bool transportUsable = false;
    String timeBefore;
    String timeAfter;
    String simClockRaw;
    String stage;
    String detail;
};

TransportCycleReport runTransportCycle();
void printTransportCycleReport(const TransportCycleReport &report);
CloudTransportReport runCloudTransportCycle();
void printCloudTransportReport(const CloudTransportReport &report);

#endif
