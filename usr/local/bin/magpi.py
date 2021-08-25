#!/usr/bin/env python3
'''
Magnum Energy Inverter/Charger Network Decoder
by Michael J. Kidd
https://github.com/linuxkidd/

- Provides decoded packet data to MQTT in JSON format.
- HomeAssistant Discovery protocol enabled.

Includes decode capacity for:
    Magnum inverter/chargers
    Magnum Remote ( RC, ARC, RTR, ARTR )
    Magnum Battery Monitor Kit ( BMK )
    Magnum Auto Gen Start ( AGS )
    Magnum Solar Charger ( PT-100 )
    Magnum AC Load Distributor ( ACLD-40 )
      - but not the remote config protocol for ACLD
      - The ACLD remote config segment is not documented

For command line option help, please run with --help.

'''
import argparse,array,json,os,queue,re,serial,signal,threading,time
import ruamel.yaml as yaml

def signal_handler(signal, frame):
    global t
    print('SIGINT received.  Terminating.')
    t.kill_received = True
    exit(0)

signal.signal(signal.SIGINT, signal_handler)


def on_mqtt_connect(client, userdata, flags, rc):
    if debug>0:
        print("MQTT Connected with code "+str(rc))

'''
Magnum Packet Details:
    RS-485, 19.2kbaud, No stop bit, 8 data bits, 1 stop bit
    Packet format:
        1: Inverter/Charger is primary and sends its data segment once 
           every 100ms
        2: After Inverter/Charger segment + ~10ms, remote sends its 
           segment, along with any accessory specific settings that need
           transmitting.
        3: Next, accessories will send a segment. Timing and frequency
           depend on the accessory.
    Scope view of a sample packet:
               10ms gap                 8 to 14ms gap
      _________   v  ____________________   v   __________________________
    _|inverter |____|remote + acc config |_____|AGS, BMK, RTR, PT or ACLD |__

'''

class SerialWatcher(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.kill_received = False

    def run(self):
        pidx=0
        delta=0
        print("Synchronizing... ",end="")
        # We look for the >50ms gap to identify the first byte of 
        # the inverter packet.
        while delta<50 and not self.kill_received:
            start  = time.time()
            mybyte   = ser.read(1)
            delta  = round((time.time()-start)*1000,1)

        print("done")

        pktarr=[[mybyte[0]]]

        while not self.kill_received:
            #time.sleep(0.0001)
            start  = time.time()
            mybyte = ser.read(1)
            delta  = round((time.time()-start)*1000,1)
            if delta<7: 
                # Inter-byte time is < 2ms == inside same packet segment
                if pidx==1 and len(pktarr[pidx])==14: 
                    # If in the 'remote' base segment, but we have 14 
                    # bytes, increment for remote accessory segment
                    pidx+=1
                    pktarr.append([])
                pktarr[pidx].append(mybyte[0])
            elif delta<=45: 
                # Inter-byte time is > 2ms but < 45ms, move to next
                # packet segment
                pidx+=1
                pktarr.append([])
                pktarr[pidx].append(mybyte[0])
            else: 
                # Inter-byte time is > 45ms, we're in the next packet 
                # with the inverter starting its segment
                q.put(pktarr)
                pidx=0
                pktarr=[[mybyte[0]]]

def mqttSend(dpkt):
    for i in dpkt:
        if i not in lastMQTT:
            lastMQTT[i]=0
        if ( dpkt[i]['pkttime'] - lastMQTT[i] ) > interval:
            mqttc.publish(topic+"/"+i+"/"+args.port[-1], json.dumps(dpkt[i]),retain=retain)
            lastMQTT[i] = int(dpkt[i]['pkttime'])

def pkt_decode(pkt):
    result={}
    for i in range(len(pkt)):
        mydata = "".join("{0:02X}".format(x) for x in pkt[i])
        params = []
        kfv=""
        if i<2:
            decoder = spec[i]
        else:
            try:
                kf = spec[i]['keyfield']
                kfv = "{0:02X}".format(pkt[i][kf])
                decoder = spec[i][kfv]
            except:
                continue

        try:
            if len(pkt[i])<decoder['minbytes']:
                return result
        except:
            pass

        try:
            if len(pkt[i])>decoder['maxbytes']:
                return result
        except:
            pass

        try:
            if len(pkt[i])!=decoder['bytes']:
                return result
        except:
            pass

        dname=parameterize_string(decoder['name'])
        result[dname] = {"name":decoder['name'], "pkttime": int(time.time())}

        try:
            params.extend(decoder['parameters'])
        except:
            pass

        for param in params:
            pname=parameterize_string(param['name'])
            result[dname][pname]={"name":param['name']}
            try:
                mybytes = get_bytes(mydata,param['byte'])
                myvalue = int(mybytes,16)
            except:
                pass

            try:
                myvalue = get_bits(myvalue,param['bit'])
                if param['type'][:4] == 'uint':
                    myvalue = int(myvalue,2)
            except:
                pass


            try:
                result[dname][pname]["unit"] = param["unit"]
            except:
                pass

            usealt = False
            try:
                comp = param['alt']['comp']
                if comp == "gt" and myvalue  > param['alt']['level']:
                    usealt = True
                if comp == "lt" and myvalue  < param['alt']['level']:
                    usealt = True
                if comp == "eq" and myvalue == param['alt']['level']:
                    usealt = True
                if comp == "le" and myvalue <= param['alt']['level']:
                    usealt = True
                if comp == "ge" and myvalue >= param['alt']['level']:
                    usealt = True

                if usealt:
                    try:
                        result[dname][pname]['value'] = param['alt']['value']
                        pname=parameterize_string(param['alt']['name'])
                        result[dname][pname]={"name":param['alt']['name']}
                    except:
                        pass

                    try:
                        myvalue += param['alt']['calibrate']
                    except:
                        pass

                    try:
                        myvalue *= param['alt']['scale']
                        if param['alt']['scale']<1:
                            # Use the round function to set proper decimal places
                            # based on the scale factor.
                            # Example: Scale factor of 0.1 shouldn't yield 10 
                            #          decimal places.
                            places  = len("{0:0.0f}".format(1/param['alt']['scale']))-1
                            myvalue = round(myvalue,places)
                    except:
                        pass

                    try:
                        if param['alt']['scaled']==1:
                            myvalue *= scalefactor
                    except:
                        pass

                    try:
                        result[dname][pname]['unit'] = param['alt']['unit']
                    except:
                        pass

                    try:
                        result[dname][pname]['value_desc'] = param['alt']['values'][myvalue]
                    except:
                        pass

            except:
                # We get here if there is no 'alt' section for the
                # parameter
                pass

            if not usealt:
                try:
                    myvalue *= param['scale']
                    if param['scale']<1:
                        # Use the round function to set proper decimal places
                        # based on the scale factor.
                        # Example: Scale factor of 0.1 shouldn't yield 10 
                        #          decimal places.
                        places  = len("{0:0.0f}".format(1/param['scale']))-1
                        myvalue = round(myvalue,places)
                except:
                    pass

                try:
                    myvalue += param['calibrate']
                except:
                    pass

                try:
                    if param['scaled']==1:
                        myvalue *= scalefactor
                except:
                    pass

                try:
                    result[dname][pname]['value_desc'] = param['values'][myvalue]
                except:
                    pass

            try:
                if param['calcscale']==1 and 'value_desc' in result[dname][pname]:
                    scalefactor=int(int("".join(filter( str.isdigit, result[dname][pname]['value_desc'] ))[2:])/12)
            except:
                pass

            result[dname][pname]['value'] = myvalue
    return result

def parameterize_string(string):
        return string.translate(string.maketrans(' /', '__', '()')).lower()

def get_bytes(mybytes,byterange):
    try:
        bset=byterange.split('-')
        sub_bytes = "".join(mybytes[i:i+2] for i in range(int(bset[0])*2, (int(bset[1])+1)*2, 2))
    except:
        sub_bytes = mybytes[ byterange * 2 : ( byterange + 1 ) * 2 ]

    return sub_bytes

def get_bits(mydata,bitrange):
    if mydata>255:
        mybits="{0:016b}".format(mydat)
    else:
        mybits="{0:08b}".format(mydata)
    try:
        bset=bitrange.split('-')
        sub_bits = mybits[ 7 - int(bset[1]) : 8 - int(bset[0]) ]
    except:
        sub_bits = mybits[ 7 - bitrange : 8 - bitrange ]

    return sub_bits

def main():

    def getLine():
        if q.empty():
            return
        packet = q.get()
        if debug>0:
            for pidx in range(len(packet)):
                print(" ".join("{0:02X}".format(x) for x in packet[pidx]),end="|")
            print("")

        decoded=pkt_decode(packet)

        if debug>1:
            print(json.dumps(decoded))

        if broker!="":
            mqttSend(decoded)

    def mainLoop():
        while True:
            getLine()
            time.sleep(0.01)

    mainLoop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--broker",   default = "",                             help="MQTT Broker to publish to")
    parser.add_argument("-d", "--debug",    default = 0, type=int, choices=[0, 1, 2], help="debug data")
    parser.add_argument("-i", "--interval", default = 1, type=int,                    help="MQTT update interval ( default 1 second )")
    parser.add_argument("-p", "--port",     default = "/dev/ttyUSB0",                 help="commuications port descriptor, e.g /dev/ttyUSB0 or COM1")
    parser.add_argument("-r", "--retain",   action = 'store_true',                    help="MQTT Retain?")
    parser.add_argument("-s", "--specfile", default = "/etc/magnum/magnum-spec.yml",  help="Magnum Protocol Spec File")
    parser.add_argument("-t", "--topic",    default = "MAGNUM",                       help="MQTT topic prefix")
    args = parser.parse_args()

    broker      = args.broker
    debug       = args.debug
    retain      = args.retain
    topic       = args.topic
    interval    = args.interval

    lastMQTT    = {}
    scalefactor=0

    if broker!="":
        import paho.mqtt.client as mqtt
        mqttc = mqtt.Client() #create new instance
        mqttc.on_connect = on_mqtt_connect

        try:
            mqttc.connect(args.broker, port=1883) #connect to broker
        except:
            print("MQTT Broker ( {0:s} ) Connection Failed".format(args.broker))

    try:
        ser = serial.Serial(port = args.port,
                         baudrate = 19200,
                         bytesize = 8,
                         timeout = 0.1)
    except:
        print('Cannot connect to port {0:s}'.format(args.port))
        exit()

    print("Loading Protocol Spec file {}.".format(args.specfile))
    with open(args.specfile,'r') as specfile:
        try:
            spec=yaml.round_trip_load(specfile)
        except yaml.YAMLError as err:
            print(err)
            exit(1)
        else:
            if debug>1:
                print(json.dumps(spec, indent=4))

    q = queue.Queue()
    t = SerialWatcher()   # Start receive thread
    t.start()

    main()
