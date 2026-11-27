#ifndef NETWORK_BRIDGE_H
#define NETWORK_BRIDGE_H

#include <Arduino.h>

bool networkSetup();
void networkMaintain();
bool networkIsConnected();
int networkSignalDbm();
String networkLocalIp();
int networkStatusCode();
const char *networkTransportName();

#endif
