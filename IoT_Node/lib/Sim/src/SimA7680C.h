#ifndef SIM_A7680C_H
#define SIM_A7680C_H

#include <Arduino.h>
#include "Config.h"

extern HardwareSerial SerialAT;

struct SimNetworkState {
    bool simReady;
    bool networkRegistered;
    bool packetAttached;
    bool gprsConnected;
    int signalDbm;
    String localIp;
    String operatorName;
};

struct SimConnectivityReport {
    bool uartReady;
    bool simReady;
    bool networkRegistered;
    bool packetAttached;
    bool gprsConnected;
    bool hasUsableIp;
    bool rawAtDirectSocketOk;
    bool rawHttpOk;
    bool internetUsable;
    int signalDbm;
    int signalCsq;
    int cipOpenCode;
    String localIp;
    String operatorName;
    String pdpContext;
    String pdpActive;
    String dnsConfig;
    String netOpen;
    String netOpenDetail;
    String rawSocketOpen;
    String rawPromptResponse;
    String rawSendResponse;
    String rawAvailableResponse;
    String rawReadResponse;
    String rawHttpStage;
    String rawHttpDetail;
    String rawHttpHeader;
    String stage;
    String detail;
};

bool setupSIM();
bool checkNetwork();
void checkInfo();
void dumpSimState(const char *stage = nullptr, bool force = false);
SimNetworkState simReadNetworkState(bool forceRefreshIp = false);
SimConnectivityReport runSimConnectivityProbe(bool forceRefreshIp = true,
                                              const struct RawSimHttpProbeResult *probeOverride = nullptr);
void printSimConnectivityReport(const SimConnectivityReport &report);
void printSimForensicAtSnapshot();
bool simHasUsableIP();
int simSignalDbm();
String simLocalIP();
int simStatusCode();
String simReadNetworkTimeRaw();

#endif
