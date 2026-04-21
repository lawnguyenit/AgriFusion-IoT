#ifndef SIM_A7680C_H
#define SIM_A7680C_H

#include <Arduino.h>
#include "Config.h"

#ifndef TINY_GSM_MODEM_A7672X
#define TINY_GSM_MODEM_A7672X
#endif
#include <TinyGsmClient.h>

extern TinyGsm modem;
extern TinyGsmClient client;

struct SimNetworkState {
    bool simReady;
    bool networkRegistered;
    bool packetAttached;
    bool gprsConnected;
    int signalDbm;
    String localIp;
    String operatorName;
};

bool setupSIM();
bool checkNetwork();
void checkInfo();
void dumpSimState(const char *stage = nullptr, bool force = false);
SimNetworkState simReadNetworkState(bool forceRefreshIp = false);
bool simHasUsableIP();
int simSignalDbm();
String simLocalIP();
int simStatusCode();

#endif
