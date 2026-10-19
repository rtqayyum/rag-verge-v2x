package v2x;

import inet.applications.contract.IApp;

simple TaskServer like IApp
{
    parameters:
        int localPort = default(4000);
        double workRate = default(8);
        double failureStart @unit(s) = default(1000s);
        double failureEnd @unit(s) = default(1000s);
        bool packetTelemetry = default(false);
        bool deadlineAdmission = default(false);
        double stateReportPeriod @unit(s) = default(0.5s);
        int stateReportBytes @unit(B) = default(96B);
        @class(v2x::TaskServer);
        @display("i=block/server");
    gates:
        input socketIn;
        output socketOut;
}
