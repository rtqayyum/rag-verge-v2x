package v2x;

import inet.applications.contract.IApp;

simple TaskClient like IApp
{
    parameters:
        string policy = default("nearest");
        int localPort = default(5000);
        int serverPort = default(4000);
        int numServers = default(2);
        string serverAddresses = default("edge[0] edge[1]");
        double startTime @unit(s) = default(2s);
        double stopTime @unit(s) = default(50s);
        double taskInterval @unit(s) = default(0.6s);
        double criticalProbability = default(0.35);
        double criticalDeadline @unit(s) = default(0.7s);
        double ordinaryDeadline @unit(s) = default(2s);
        double minWork = default(1);
        double maxWork = default(2);
        string serverRates = default("16 20");
        string serverXs = default("250 750");
        string serverYs = default("500 500");
        double baseNetworkDelay @unit(s) = default(0.02s);
        double crossCellBackhaulDelay @unit(s) = default(0.08s);
        // Controlled interruption charged when SUMO mobility crosses the
        // nearest roadside-cell boundary while a task is outstanding.
        double handoverInterruption @unit(s) = default(0.05s);
        double handoverRiskPenalty @unit(s) = default(0.20s);
        double failureRiskPenalty @unit(s) = default(1s);
        double forecastUncertainty @unit(s) = default(0.4s);
        double replicationBoundaryMeters @unit(m) = default(80m);
        double replicationReliabilityThreshold = default(0.9);
        double replicationMaxAlternateQueue @unit(s) = default(0.35s);
        // VERGE-V2X guard: probability is estimated from predicted delay and
        // feedback reliability; an infeasible critical task is explicitly recorded.
        double vergeReliabilityTarget = default(0.90);
        double vergeDelayUncertainty @unit(s) = default(0.08s);
        // RAG-evolved policy portfolio switches to delay-first dispatch once
        // the mean observed edge queue exceeds this threshold.
        double ragOverloadQueueThreshold @unit(s) = default(0.18s);
        int requestBytes @unit(B) = default(1200B);
        int responseBytes @unit(B) = default(240B);
        @class(v2x::TaskClient);
        @display("i=block/source");
    gates:
        input socketIn;
        output socketOut;
}
