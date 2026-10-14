package v2x;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.networklayer.ipv4.RoutingTableRecorder;
import inet.node.ethernet.Eth10G;
import inet.node.inet.StandardHost;
import inet.node.inet.Router;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import simu5g.corenetwork.bearerConfigurator.BearerConfigurator;
import simu5g.corenetwork.coreControl.CoreControl;
import simu5g.nodes.NrUe;
import simu5g.nodes.gNodeB;
import simu5g.nodes.Upf;
import simu5g.world.radio.LteChannelControl;

// Configurable MEC-enabled roadside 5G access points. The UEs traverse cells
// using measured SUMO trajectories. Each roadside access point has a gNB and
// an edge compute host connected through its own intermediate UPF.
network V2XNetwork
{
    parameters:
        **.cellularNic.hasSdap = default(true);
        int numUe = default(8);
        int numRsu = default(2);
        @display("bgb=1100,650");
    submodules:
        channelControl: LteChannelControl;
        routingRecorder: RoutingTableRecorder;
        configurator: Ipv4NetworkConfigurator;
        binder: Binder;
        coreControl: CoreControl;
        bearerConfigurator: BearerConfigurator;
        carrierAggregation: CarrierAggregation;
        upf: Upf;
        iUpf[numRsu]: Upf;
        router: Router;
        edge[numRsu]: StandardHost;
        gnb[numRsu]: gNodeB;
        ue[numUe]: NrUe;
    connections:
        for i=0..numRsu-1 {
            upf.pppg++ <--> Eth10G <--> iUpf[i].pppg++;
            iUpf[i].pppg++ <--> Eth10G <--> gnb[i].ppp;
            edge[i].pppg++ <--> Eth10G <--> router.pppg++;
        }
        router.pppg++ <--> Eth10G <--> upf.dnPppg;
        for i=0..numRsu-1, for j=i+1..numRsu-1 {
            gnb[i].x2++ <--> Eth10G <--> gnb[j].x2++;
        }
}
