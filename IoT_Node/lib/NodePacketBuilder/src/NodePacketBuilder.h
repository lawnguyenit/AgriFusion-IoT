#ifndef NODE_PACKET_BUILDER_H
#define NODE_PACKET_BUILDER_H

#include <Arduino.h>

class Sht30Service;

class NodePacketBuilder {
public:
    explicit NodePacketBuilder(Sht30Service &sht30Service);

    String buildCombinedNodePacket(const String &npkPayloadJson,
                                   bool npkAlarm,
                                   const String &firmwareVersion,
                                   const String &runningPartition) const;

private:
    Sht30Service &_sht30Service;
};

#endif
