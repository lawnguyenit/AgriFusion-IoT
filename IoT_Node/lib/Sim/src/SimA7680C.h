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

bool setupSIM();
bool checkNetwork();
void checkInfo();
void dumpSimState(const char *stage = nullptr, bool force = false);
int simSignalDbm();
String simLocalIP();
int simStatusCode();

#endif
