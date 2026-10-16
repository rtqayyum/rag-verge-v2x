import inet.common.INETDefs;
import inet.common.packet.chunk.Chunk;

namespace v2x;

class TaskChunk extends inet::FieldsChunk
{
    int taskId;
    int clientId;
    int serverId;
    bool response;
    bool critical;
    simtime_t createdAt;
    simtime_t deadlineAt;
    double workUnits;
    double queueSeconds;
    int responseBytes;
    bool telemetry;
    bool subscribe;
    bool unsubscribe;
    int reportSequence;
    simtime_t reportGeneratedAt;
    simtime_t reportBusyUntil;
}
