#include <algorithm>
#include <chrono>
#include <cmath>
#include <map>
#include <sstream>
#include <vector>

#include "TaskPacket_m.h"
#include "inet/common/INETDefs.h"
#include "inet/common/packet/Packet.h"
#include "inet/mobility/contract/IMobility.h"
#include "inet/networklayer/common/L3AddressResolver.h"
#include "inet/networklayer/common/L3AddressTag_m.h"
#include "inet/transportlayer/common/L4PortTag_m.h"
#include "inet/transportlayer/contract/udp/UdpSocket.h"

using namespace omnetpp;
using namespace inet;

namespace v2x {

// MEC servers publish their projected busy-until time as a congestion
// telemetry signal.  In deployment this is a lightweight RSU/MEC control
// message; the packet model shares it directly so each UE observes the same
// state without waiting for its own delayed task response.
static std::vector<simtime_t> advertisedEdgeFreeAt;

static double advertisedQueueDelay(int server) {
    if (server < 0 || server >= static_cast<int>(advertisedEdgeFreeAt.size()))
        return 0.0;
    return std::max(0.0, (advertisedEdgeFreeAt[server] - simTime()).dbl());
}

struct SentTask {
    simtime_t createdAt;
    simtime_t deadlineAt;
    bool critical;
    int cellAtSend;
    int serverId;
    bool timeoutCharged;
};

class TaskClient : public cSimpleModule, public UdpSocket::ICallback {
    UdpSocket socket;
    cMessage *tick = nullptr;
    cMessage *endTick = nullptr;
    bool subscribed = false;
    std::vector<L3Address> edges;
    std::vector<double> serverRates, serverXs, serverYs;
    std::vector<double> queueEstimate;
    std::vector<simtime_t> stateBusyUntil, stateGeneratedAt;
    std::vector<int> stateSequence;
    std::vector<double> stateArrivalRate;
    // RAG-VERGE keeps a local workload ledger between delayed server reports.
    // It is used only to decide whether the offline-evolved portfolio should
    // enter its overload branch; static baselines retain their original inputs.
    std::vector<double> ragQueueEstimate;
    std::vector<simtime_t> ragQueueUpdatedAt;
    std::vector<double> reliability;
    std::vector<int> selected;
    std::map<int, SentTask> outstanding;
    int nextId = 0;
    int offeredCritical = 0, offeredOrdinary = 0;
    double totalOfferedWorkUnits = 0.0;
    int successCritical = 0, successOrdinary = 0;
    int lateCritical = 0, lateOrdinary = 0;
    int crossedCell = 0, responses = 0, replicatedTasks = 0;
    int vergeShieldFallbacks = 0, vergeSafeReplications = 0, ragOverloadFallbacks = 0;
    int handoverEvents = 0, previousCell = -1;
    int stateReportsReceived = 0, stateReportsOutOfOrder = 0;
    int stateDecisionsWithReport = 0, stateDecisionsWithoutReport = 0;
    int stateSubscriptionsSent = 0;
    long long stateBytesReceived = 0, stateSubscriptionBytesSent = 0;
    double totalStateAgeAtDecision = 0.0;
    int decisionCount = 0;
    double totalLatency = 0.0, totalObservedQueueDelay = 0.0, maxObservedQueueDelay = 0.0;
    long long totalDecisionNanoseconds = 0;
    cOutVector *responseLatencyVector = nullptr;
    cOutVector *observedQueueDelayVector = nullptr;
    cOutVector *stateAgeVector = nullptr;

    std::vector<std::string> splitWords(const char *parameter) const {
        std::istringstream stream(par(parameter).stdstringValue());
        std::vector<std::string> values;
        for (std::string value; stream >> value;) values.push_back(value);
        return values;
    }

    std::vector<double> splitNumbers(const char *parameter) const {
        std::istringstream stream(par(parameter).stdstringValue());
        std::vector<double> values;
        for (double value; stream >> value;) values.push_back(value);
        return values;
    }

    int nearestServer(const Coord& position) const {
        double bestDistance = 1e99;
        int best = 0;
        for (int j = 0; j < par("numServers").intValue(); ++j) {
            double dx = position.x - serverXs[j];
            double dy = position.y - serverYs[j];
            double distance = dx * dx + dy * dy;
            if (distance < bestDistance) { bestDistance = distance; best = j; }
        }
        return best;
    }

    int currentCell() const {
        auto *mobility = check_and_cast<IMobility *>(getParentModule()->getSubmodule("mobility"));
        return nearestServer(mobility->getCurrentPosition());
    }

    double predictedDelay(int server, double work) const {
        auto *mobility = check_and_cast<IMobility *>(getParentModule()->getSubmodule("mobility"));
        int cell = currentCell();
        return 2.0 * par("baseNetworkDelay").doubleValue()
            + (server != cell ? 2.0 * par("crossCellBackhaulDelay").doubleValue() : 0.0)
            + queueEstimate[server] + work / serverRates[server];
    }

    double deadlineProbability(int server, double work, simtime_t deadline) const {
        double slack = (deadline - simTime()).dbl();
        double standardized = (slack - predictedDelay(server, work)) /
            par("vergeDelayUncertainty").doubleValue();
        double delaySuccess = 1.0 / (1.0 + std::exp(-standardized));
        return reliability[server] * delaySuccess;
    }

    void refreshRagQueue(int server) {
        simtime_t elapsed = simTime() - ragQueueUpdatedAt[server];
        ragQueueEstimate[server] = std::max(0.0, ragQueueEstimate[server] - elapsed.dbl());
        ragQueueUpdatedAt[server] = simTime();
    }

    bool ragOverloadActive(const std::string& policy) {
        if (policy != "ragverge")
            return false;
        double meanQueue = 0.0;
        for (int j = 0; j < par("numServers").intValue(); ++j) {
            refreshRagQueue(j);
            // Use the larger of local reservation and fresh MEC telemetry.
            ragQueueEstimate[j] = std::max(ragQueueEstimate[j], advertisedQueueDelay(j));
            meanQueue += ragQueueEstimate[j];
        }
        meanQueue /= std::max<size_t>(1, ragQueueEstimate.size());
        return meanQueue >= par("ragOverloadQueueThreshold").doubleValue();
    }

    void sendStateSubscription(bool unsubscribe) {
        for (int server = 0; server < par("numServers").intValue(); ++server) {
            auto header = makeShared<TaskChunk>();
            header->setTelemetry(true);
            header->setSubscribe(!unsubscribe);
            header->setUnsubscribe(unsubscribe);
            header->setClientId(getParentModule()->getIndex());
            header->setServerId(server);
            header->setChunkLength(B(par("stateSubscriptionBytes").intValue()));
            auto *packet = new Packet(unsubscribe ? "state-unsubscribe" : "state-subscribe");
            packet->insertAtBack(header);
            socket.sendTo(packet, edges[server], par("serverPort").intValue());
            ++stateSubscriptionsSent;
            stateSubscriptionBytesSent += par("stateSubscriptionBytes").intValue();
        }
    }

    double stateQueueDelay(int server, bool ageAware) const {
        if (stateSequence[server] < 0)
            return ageAware ? 1.0 : 0.0;
        double remaining = std::max(0.0, (stateBusyUntil[server] - simTime()).dbl());
        double age = std::max(0.0, (simTime() - stateGeneratedAt[server]).dbl());
        return remaining + (ageAware ? par("agePenalty").doubleValue() *
                            stateArrivalRate[server] * age : 0.0);
    }

    void recordStateDecision(int server) {
        if (stateSequence[server] < 0) {
            ++stateDecisionsWithoutReport;
            return;
        }
        ++stateDecisionsWithReport;
        double age = std::max(0.0, (simTime() - stateGeneratedAt[server]).dbl());
        totalStateAgeAtDecision += age;
        stateAgeVector->record(age);
    }

    int chooseServer(double work, bool critical, simtime_t deadline) {
        auto *mobility = check_and_cast<IMobility *>(getParentModule()->getSubmodule("mobility"));
        double x = mobility->getCurrentPosition().x;
        double vx = mobility->getCurrentVelocity().x;
        int cell = currentCell();
        std::string policy = par("policy").stdstringValue();
        if (policy == "staleleast" || policy == "power2" || policy == "ageaware" ||
            policy == "freshpower2" ||
            policy == "oracleleast") {
            if (!par("packetTelemetry").boolValue() && policy != "oracleleast")
                throw cRuntimeError("Policy %s requires packetTelemetry=true", policy.c_str());
            int first = 0, second = par("numServers").intValue();
            if (policy == "power2" || policy == "freshpower2") {
                first = intuniform(0, par("numServers").intValue() - 1, 1);
                second = intuniform(0, par("numServers").intValue() - 2, 1);
                if (second >= first) ++second;
            }
            int best = -1;
            double bestScore = 1e99;
            for (int j = 0; j < par("numServers").intValue(); ++j) {
                if ((policy == "power2" || policy == "freshpower2") &&
                    j != first && j != second) continue;
                // All MEC hosts use the same routed UPF path in this topology;
                // do not add an unmeasured cross-cell backhaul cost.
                double queue = policy == "oracleleast" ? advertisedQueueDelay(j) :
                    stateQueueDelay(j, policy == "ageaware" || policy == "freshpower2");
                // FreshPower2 preserves power-of-two diversification while
                // charging a criticality-weighted uncertainty cost for stale
                // telemetry. The age term is only applied inside the sampled
                // set, so the policy retains the load-balancing benefit of d=2.
                if (policy == "freshpower2" && stateSequence[j] >= 0) {
                    double age = std::max(0.0, (simTime() - stateGeneratedAt[j]).dbl());
                    double boost = critical ? par("freshnessCriticalBoost").doubleValue() : 1.0;
                    queue += par("freshnessPenalty").doubleValue() * boost *
                        stateArrivalRate[j] * age;
                }
                double score = 2.0 * par("baseNetworkDelay").doubleValue() +
                    queue + work / serverRates[j];
                if (score < bestScore) { bestScore = score; best = j; }
            }
            if (policy != "oracleleast") recordStateDecision(best);
            return best;
        }
        if (policy == "nearest")
            return cell;
        // In sustained overload, a conservative reliability guard can reject
        // every edge. The evolved portfolio then dispatches by earliest
        // predicted completion, while retaining VERGE below this threshold.
        bool overloadFallback = ragOverloadActive(policy);
        if (overloadFallback) ++ragOverloadFallbacks;

        double bestScore = 1e99;
        double bestSafeScore = 1e99;
        int best = 0, bestSafe = -1;
        for (int j = 0; j < par("numServers").intValue(); ++j) {
            double predicted = predictedDelay(j, work);
            double score = predicted;
            if (!overloadFallback && (policy == "risk" || policy == "replicate" ||
                                      policy == "verge" || policy == "ragverge")) {
                double futureX = x + vx * predicted;
                Coord futurePosition = mobility->getCurrentPosition();
                futurePosition.x = futureX;
                int futureCell = nearestServer(futurePosition);
                double distanceToFutureSite = std::hypot(
                    futureX - serverXs[j], futurePosition.y - serverYs[j]);
                double margin = std::abs(vx) * par("forecastUncertainty").doubleValue();
                bool nearBoundary = distanceToFutureSite <= margin;
                if (j != futureCell || nearBoundary)
                    score += par("handoverRiskPenalty").doubleValue();
                score += par("failureRiskPenalty").doubleValue() * (1.0 - reliability[j]);
            }
            else if (policy != "earliest" && policy != "ragverge")
                throw cRuntimeError("Unknown task policy '%s'", policy.c_str());
            if (score < bestScore) { bestScore = score; best = j; }
            if ((policy == "verge" || (policy == "ragverge" && !overloadFallback)) && critical &&
                deadlineProbability(j, work, deadline) >= par("vergeReliabilityTarget").doubleValue() &&
                score < bestSafeScore) {
                bestSafeScore = score;
                bestSafe = j;
            }
        }
        if ((policy == "verge" || (policy == "ragverge" && !overloadFallback)) && critical) {
            if (bestSafe >= 0) return bestSafe;
            ++vergeShieldFallbacks;
        }
        return best;
    }

    void sendTask(int id, int server, bool critical, double work, simtime_t deadline) {
        auto header = makeShared<TaskChunk>();
        header->setTaskId(id);
        header->setClientId(getParentModule()->getIndex());
        header->setServerId(server);
        header->setResponse(false);
        header->setTelemetry(false);
        header->setCritical(critical);
        header->setCreatedAt(simTime());
        header->setDeadlineAt(deadline);
        header->setWorkUnits(work);
        header->setResponseBytes(par("responseBytes").intValue());
        header->setChunkLength(B(par("requestBytes").intValue()));
        auto *packet = new Packet("edge-task");
        packet->insertAtBack(header);
        socket.sendTo(packet, edges[server], par("serverPort").intValue());
        if (par("policy").stdstringValue() == "ragverge") {
            refreshRagQueue(server);
            ragQueueEstimate[server] += work / serverRates[server];
        }
    }

  protected:
    int numInitStages() const override { return inet::NUM_INIT_STAGES; }
    void initialize(int stage) override {
        if (stage != inet::INITSTAGE_APPLICATION_LAYER)
            return;
        socket.setOutputGate(gate("socketOut"));
        socket.bind(par("localPort").intValue() + getParentModule()->getIndex());
        socket.setCallback(this);
        int server = getParentModule()->getIndex();
        if (server >= static_cast<int>(advertisedEdgeFreeAt.size()))
            advertisedEdgeFreeAt.resize(server + 1, SIMTIME_ZERO);
        int numServers = par("numServers").intValue();
        edges.resize(numServers);
        queueEstimate.assign(numServers, 0.0);
        stateBusyUntil.assign(numServers, SIMTIME_ZERO);
        stateGeneratedAt.assign(numServers, SIMTIME_ZERO);
        stateSequence.assign(numServers, -1);
        stateArrivalRate.assign(numServers, 0.0);
        ragQueueEstimate.assign(numServers, 0.0);
        ragQueueUpdatedAt.assign(numServers, simTime());
        reliability.assign(numServers, 1.0);
        selected.assign(numServers, 0);
        serverRates = splitNumbers("serverRates");
        serverXs = splitNumbers("serverXs");
        serverYs = splitNumbers("serverYs");
        auto serverAddresses = splitWords("serverAddresses");
        if (serverRates.size() != numServers || serverXs.size() != numServers ||
            serverYs.size() != numServers || serverAddresses.size() != numServers)
            throw cRuntimeError("Server parameter count must equal numServers");
        for (int j = 0; j < numServers; ++j)
            edges[j] = L3AddressResolver().resolve(serverAddresses[j].c_str());
        previousCell = currentCell();
        responseLatencyVector = new cOutVector("responseLatency");
        observedQueueDelayVector = new cOutVector("observedQueueDelay");
        stateAgeVector = new cOutVector("stateAgeAtDecision");
        tick = new cMessage("generateTask");
        endTick = new cMessage("endVehicleActivity");
        if (par("startTime").doubleValue() < par("stopTime").doubleValue()) {
            scheduleAt(par("startTime"), tick);
            if (par("packetTelemetry").boolValue())
                scheduleAt(par("stopTime"), endTick);
        }
    }

    void handleMessage(cMessage *message) override {
        if (message == endTick) {
            if (subscribed) sendStateSubscription(true);
            return;
        }
        if (message == tick) {
            if (par("packetTelemetry").boolValue() && !subscribed) {
                sendStateSubscription(false);
                subscribed = true;
                if (simTime() + 0.1 < par("stopTime"))
                    scheduleAt(simTime() + 0.1, tick);
                return;
            }
            int current = currentCell();
            if (current != previousCell) ++handoverEvents;
            previousCell = current;
            for (auto &[id, task] : outstanding) {
                if (!task.timeoutCharged && simTime() > task.deadlineAt) {
                    reliability[task.serverId] *= 0.8;
                    task.timeoutCharged = true;
                }
            }
            int id = nextId++;
            bool critical = uniform(0, 1, 0) < par("criticalProbability").doubleValue();
            double work = uniform(par("minWork").doubleValue(), par("maxWork").doubleValue(), 0);
            simtime_t deadline = simTime() + (critical ? par("criticalDeadline") : par("ordinaryDeadline"));
            auto decisionStart = std::chrono::steady_clock::now();
            int server = chooseServer(work, critical, deadline);
            totalDecisionNanoseconds += std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - decisionStart).count();
            ++decisionCount;
            outstanding[id] = {simTime(), deadline, critical, currentCell(), server, false};
            ++selected[server];
            if (critical) ++offeredCritical; else ++offeredOrdinary;
            totalOfferedWorkUnits += work;
            sendTask(id, server, critical, work, deadline);
            if (critical && par("policy").stdstringValue() == "replicate") {
                auto *mobility = check_and_cast<IMobility *>(getParentModule()->getSubmodule("mobility"));
                Coord predictedPosition = mobility->getCurrentPosition();
                predictedPosition.x += mobility->getCurrentVelocity().x *
                    par("criticalDeadline").doubleValue();
                bool boundaryRisk = nearestServer(predictedPosition) != currentCell();
                bool failureRisk = reliability[server] < par("replicationReliabilityThreshold").doubleValue();
                int alternate = -1;
                double bestAlternative = -1.0;
                for (int j = 0; j < par("numServers").intValue(); ++j) {
                    if (j == server) continue;
                    double probability = deadlineProbability(j, work, deadline);
                    if (probability > bestAlternative) { bestAlternative = probability; alternate = j; }
                }
                if ((boundaryRisk || failureRisk) &&
                    alternate >= 0 && queueEstimate[alternate] < par("replicationMaxAlternateQueue").doubleValue()) {
                    sendTask(id, alternate, critical, work, deadline);
                    ++replicatedTasks;
                }
            }
            const std::string policy = par("policy").stdstringValue();
            if (critical && (policy == "verge" || (policy == "ragverge" && !ragOverloadActive(policy)))) {
                int alternate = -1;
                double bestAlternative = -1.0;
                for (int j = 0; j < par("numServers").intValue(); ++j) {
                    if (j == server) continue;
                    double probability = deadlineProbability(j, work, deadline);
                    if (probability > bestAlternative) { bestAlternative = probability; alternate = j; }
                }
                double primaryProbability = deadlineProbability(server, work, deadline);
                double alternateProbability = alternate >= 0 ? deadlineProbability(alternate, work, deadline) : 0.0;
                double combinedProbability = 1.0 - (1.0 - primaryProbability) *
                    (1.0 - alternateProbability);
                if (primaryProbability < par("vergeReliabilityTarget").doubleValue() &&
                    combinedProbability >= par("vergeReliabilityTarget").doubleValue() &&
                    alternate >= 0 && queueEstimate[alternate] < par("replicationMaxAlternateQueue").doubleValue()) {
                    sendTask(id, alternate, critical, work, deadline);
                    ++replicatedTasks;
                    ++vergeSafeReplications;
                }
            }
            simtime_t next = simTime() + par("taskInterval");
            if (next < par("stopTime")) scheduleAt(next, tick);
        }
        else
            socket.processMessage(message);
    }

    void socketDataArrived(UdpSocket *, Packet *packet) override {
        auto header = packet->peekAtFront<TaskChunk>();
        if (header->getTelemetry()) {
            if (!header->getSubscribe() && !header->getUnsubscribe()) {
                int server = header->getServerId();
                if (server >= 0 && server < par("numServers").intValue()) {
                    if (header->getReportSequence() > stateSequence[server]) {
                        if (stateSequence[server] >= 0) {
                            double elapsed = (header->getReportGeneratedAt() - stateGeneratedAt[server]).dbl();
                            if (elapsed > 0) {
                                double newlyQueued = std::max(0.0,
                                    (header->getReportBusyUntil() -
                                     std::max(stateBusyUntil[server], header->getReportGeneratedAt())).dbl());
                                stateArrivalRate[server] = 0.5 * stateArrivalRate[server] +
                                    0.5 * newlyQueued / elapsed;
                            }
                        }
                        stateSequence[server] = header->getReportSequence();
                        stateGeneratedAt[server] = header->getReportGeneratedAt();
                        stateBusyUntil[server] = header->getReportBusyUntil();
                        ++stateReportsReceived;
                        stateBytesReceived += packet->getByteLength();
                    }
                    else ++stateReportsOutOfOrder;
                }
            }
            delete packet;
            return;
        }
        auto it = outstanding.find(header->getTaskId());
        if (header->getResponse() && it != outstanding.end()) {
            SentTask task = it->second;
            bool crossedBoundary = currentCell() != task.cellAtSend;
            double interruption = crossedBoundary ? par("handoverInterruption").doubleValue() : 0.0;
            double latency = (simTime() - task.createdAt).dbl() + interruption;
            totalLatency += latency;
            responseLatencyVector->record(latency);
            ++responses;
            if (crossedBoundary) ++crossedCell;
            if (simTime() + interruption <= task.deadlineAt) {
                if (task.critical) ++successCritical; else ++successOrdinary;
                int responder = header->getServerId();
                reliability[responder] = 0.9 * reliability[responder] + 0.1;
            }
            else {
                if (task.critical) ++lateCritical; else ++lateOrdinary;
            }
            int server = header->getServerId();
            double observedQueueDelay = header->getQueueSeconds();
            queueEstimate[server] = 0.7 * queueEstimate[server] + 0.3 * observedQueueDelay;
            if (par("policy").stdstringValue() == "ragverge") {
                refreshRagQueue(server);
                ragQueueEstimate[server] = 0.5 * ragQueueEstimate[server] + 0.5 * observedQueueDelay;
            }
            totalObservedQueueDelay += observedQueueDelay;
            maxObservedQueueDelay = std::max(maxObservedQueueDelay, observedQueueDelay);
            observedQueueDelayVector->record(observedQueueDelay);
            outstanding.erase(it);
        }
        delete packet;
    }
    void socketErrorArrived(UdpSocket *, Indication *indication) override { delete indication; }
    void socketClosed(UdpSocket *) override {}

    void finish() override {
        recordScalar("offeredCritical", offeredCritical);
        recordScalar("offeredOrdinary", offeredOrdinary);
        recordScalar("totalOfferedWorkUnits", totalOfferedWorkUnits);
        recordScalar("successCritical", successCritical);
        recordScalar("successOrdinary", successOrdinary);
        recordScalar("lateCritical", lateCritical);
        recordScalar("lateOrdinary", lateOrdinary);
        recordScalar("unanswered", outstanding.size());
        recordScalar("responseCount", responses);
        recordScalar("replicatedTasks", replicatedTasks);
        recordScalar("vergeShieldFallbacks", vergeShieldFallbacks);
        recordScalar("vergeSafeReplications", vergeSafeReplications);
        recordScalar("ragOverloadFallbacks", ragOverloadFallbacks);
        recordScalar("crossedCellWhilePending", crossedCell);
        recordScalar("handoverEvents", handoverEvents);
        recordScalar("stateReportsReceived", stateReportsReceived);
        recordScalar("stateReportsOutOfOrder", stateReportsOutOfOrder);
        recordScalar("stateDecisionsWithReport", stateDecisionsWithReport);
        recordScalar("stateDecisionsWithoutReport", stateDecisionsWithoutReport);
        recordScalar("stateSubscriptionsSent", stateSubscriptionsSent);
        recordScalar("stateBytesReceived", stateBytesReceived);
        recordScalar("stateSubscriptionBytesSent", stateSubscriptionBytesSent);
        recordScalar("meanStateAgeAtDecision", stateDecisionsWithReport ?
            totalStateAgeAtDecision / stateDecisionsWithReport : 0.0);
        recordScalar("meanResponseLatency", responses ? totalLatency / responses : 0.0);
        recordScalar("totalResponseLatency", totalLatency);
        recordScalar("meanObservedQueueDelay", responses ? totalObservedQueueDelay / responses : 0.0);
        recordScalar("totalObservedQueueDelay", totalObservedQueueDelay);
        recordScalar("maxObservedQueueDelay", maxObservedQueueDelay);
        recordScalar("meanDecisionTimeUs", decisionCount ?
            (totalDecisionNanoseconds / 1000.0) / decisionCount : 0.0);
        for (int j = 0; j < par("numServers").intValue(); ++j) {
            std::string server = std::to_string(j + 1);
            recordScalar(("selectedServer" + server).c_str(), selected[j]);
            recordScalar(("reliabilityServer" + server).c_str(), reliability[j]);
        }
    }
  public:
    ~TaskClient() override {
        cancelAndDelete(tick);
        cancelAndDelete(endTick);
        delete responseLatencyVector;
        delete observedQueueDelayVector;
        delete stateAgeVector;
    }
};

Define_Module(TaskClient);

struct PendingResponse {
    int taskId, clientId, serverId, responseBytes;
    bool critical;
    simtime_t createdAt, deadlineAt;
    double workUnits, queueSeconds;
    L3Address destination;
    int destinationPort;
};

class TaskServer : public cSimpleModule, public UdpSocket::ICallback {
    UdpSocket socket;
    cMessage *reportTick = nullptr;
    simtime_t freeAt = 0;
    std::map<cMessage *, PendingResponse *> pending;
    std::map<int, std::pair<L3Address, int>> subscribers;
    int reportSequence = 0, stateReportsSent = 0;
    int stateSubscriptionsReceived = 0;
    long long stateBytesSent = 0;
    int received = 0, droppedDuringFailure = 0, sent = 0;
    double totalWorkReceived = 0.0, totalQueueDelay = 0.0, maxQueueDelay = 0.0;

    void sendStateReport(const L3Address& destination, int port) {
        auto header = makeShared<TaskChunk>();
        header->setTelemetry(true);
        header->setSubscribe(false);
        header->setUnsubscribe(false);
        header->setServerId(getParentModule()->getIndex());
        header->setReportSequence(reportSequence);
        header->setReportGeneratedAt(simTime());
        header->setReportBusyUntil(freeAt);
        header->setChunkLength(B(par("stateReportBytes").intValue()));
        auto *packet = new Packet("state-report");
        packet->insertAtBack(header);
        socket.sendTo(packet, destination, port);
        ++stateReportsSent;
        stateBytesSent += par("stateReportBytes").intValue();
    }

  protected:
    int numInitStages() const override { return inet::NUM_INIT_STAGES; }
    void initialize(int stage) override {
        if (stage != inet::INITSTAGE_APPLICATION_LAYER) return;
        socket.setOutputGate(gate("socketOut"));
        socket.bind(par("localPort"));
        socket.setCallback(this);
        if (par("packetTelemetry").boolValue()) {
            if (par("stateReportPeriod").doubleValue() <= 0.0)
                throw cRuntimeError("stateReportPeriod must be positive");
            reportTick = new cMessage("stateReportTick");
            scheduleAt(simTime() + par("stateReportPeriod"), reportTick);
        }
    }
    void handleMessage(cMessage *message) override {
        if (message == reportTick) {
            ++reportSequence;
            for (const auto& [client, endpoint] : subscribers)
                sendStateReport(endpoint.first, endpoint.second);
            scheduleAt(simTime() + par("stateReportPeriod"), reportTick);
            return;
        }
        auto it = pending.find(message);
        if (it == pending.end()) { socket.processMessage(message); return; }
        PendingResponse *data = it->second;
        auto header = makeShared<TaskChunk>();
        header->setTaskId(data->taskId);
        header->setClientId(data->clientId);
        header->setServerId(data->serverId);
        header->setResponse(true);
        header->setTelemetry(false);
        header->setCritical(data->critical);
        header->setCreatedAt(data->createdAt);
        header->setDeadlineAt(data->deadlineAt);
        header->setWorkUnits(data->workUnits);
        header->setQueueSeconds(data->queueSeconds);
        header->setResponseBytes(data->responseBytes);
        header->setChunkLength(B(data->responseBytes));
        auto *packet = new Packet("edge-result");
        packet->insertAtBack(header);
        socket.sendTo(packet, data->destination, data->destinationPort);
        ++sent;
        delete data;
        pending.erase(it);
        delete message;
    }
    void socketDataArrived(UdpSocket *, Packet *packet) override {
        auto header = packet->peekAtFront<TaskChunk>();
        if (header->getTelemetry()) {
            if (header->getSubscribe()) {
                subscribers[header->getClientId()] = {
                    packet->getTag<L3AddressInd>()->getSrcAddress(),
                    packet->getTag<L4PortInd>()->getSrcPort()
                };
                ++stateSubscriptionsReceived;
                ++reportSequence;
                const auto& endpoint = subscribers.at(header->getClientId());
                sendStateReport(endpoint.first, endpoint.second);
            }
            else if (header->getUnsubscribe())
                subscribers.erase(header->getClientId());
            delete packet;
            return;
        }
        if (!header->getResponse()) {
            ++received;
            totalWorkReceived += header->getWorkUnits();
            if (simTime() >= par("failureStart") && simTime() < par("failureEnd"))
                ++droppedDuringFailure;
            else {
                simtime_t start = std::max(simTime(), freeAt);
                simtime_t finishAt = start + header->getWorkUnits() / par("workRate").doubleValue();
                freeAt = finishAt;
                advertisedEdgeFreeAt[getParentModule()->getIndex()] = freeAt;
                double queueDelay = (start - simTime()).dbl();
                totalQueueDelay += queueDelay;
                maxQueueDelay = std::max(maxQueueDelay, queueDelay);
                auto *data = new PendingResponse{
                    header->getTaskId(), header->getClientId(), header->getServerId(),
                    header->getResponseBytes(), header->getCritical(), header->getCreatedAt(),
                    header->getDeadlineAt(), header->getWorkUnits(), queueDelay,
                    packet->getTag<L3AddressInd>()->getSrcAddress(),
                    packet->getTag<L4PortInd>()->getSrcPort()
                };
                auto *done = new cMessage("taskComputed");
                pending[done] = data;
                scheduleAt(finishAt, done);
            }
        }
        delete packet;
    }
    void socketErrorArrived(UdpSocket *, Indication *indication) override { delete indication; }
    void socketClosed(UdpSocket *) override {}
    void finish() override {
        recordScalar("tasksReceived", received);
        recordScalar("tasksDroppedFailure", droppedDuringFailure);
        recordScalar("resultsSent", sent);
        recordScalar("meanQueueDelay", sent ? totalQueueDelay / sent : 0.0);
        recordScalar("totalQueueDelay", totalQueueDelay);
        recordScalar("maxQueueDelay", maxQueueDelay);
        recordScalar("serviceWorkUnits", totalWorkReceived);
        recordScalar("estimatedBusyFraction", std::min(1.0,
            totalWorkReceived / par("workRate").doubleValue() / simTime().dbl()));
        recordScalar("stateReportsSent", stateReportsSent);
        recordScalar("stateBytesSent", stateBytesSent);
        recordScalar("stateSubscriptionsReceived", stateSubscriptionsReceived);
    }
  public:
    ~TaskServer() override {
        cancelAndDelete(reportTick);
        for (auto &[message, data] : pending) { cancelAndDelete(message); delete data; }
    }
};

Define_Module(TaskServer);

} // namespace v2x
