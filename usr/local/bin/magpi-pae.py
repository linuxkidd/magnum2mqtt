#!/usr/bin/env python3

'''
MagPy - an application to interface with Magnum inverters
The application decodes the MagNet data protocol to display
data for all devices connected and active.

This program was initially inspired by Chris (aka user cpfl) Midnightsolar forum.

Created     13 Jun 2015
Modified    26 Feb 2018

@author: Paul Alting van Geusau
@author: Liam O'Brien

---------------------------------------------------------------------------------------------------------------------------
    Data capture from actual MagNet with MS4448PAE, RTR, AGS and BMK devices:
                                                                                                                    Bytes  Total   Packet Marker
    Inverter            40 00 01 F8 00 04 77 00 01 00 33 17 2E 22 73 01 00 01 02 58 00 FF                            22
    Remote_B+A0+A1      00 05 50 94 64 1E 16 08 00 D5 9B 84 07 19 17 26 14 00 73 00 A0 A1 02 35 FC 00 7D             27    = 49    pos[41] = 0xA0

    Inverter            40 00 01 F8 00 04 77 00 01 00 33 17 2E 22 73 01 00 01 02 58 00 FE                            22
    Remote_B+A1+A2      00 05 50 94 64 1E 16 08 00 D5 9B 84 07 19 20 20 90 3C 3C 78 A1 A2 01 00 00 00 00             27    = 49    pos[41] = 0xA1

    Inverter            40 00 01 F8 00 04 77 00 01 00 33 17 2E 22 73 01 00 01 02 58 00 FF                            22
    Remote_B+A2+RTR     00 05 50 94 64 1E 16 08 00 D5 9B 84 07 19 00 64 00 3C 0A 3C A2 91 01                         23    = 45    pos[41] = 0xA2

    Inverter            40 00 01 F8 00 04 77 00 01 00 33 17 2E 22 73 01 00 01 02 58 00 FF                            22
    Remote_B+A3         00 05 50 94 64 1E 16 08 00 D5 9B 84 07 19 50 28 00 20 0A 00 A3                               21    = 43    pos[41] = 0xA3

    Inverter            40 00 01 F8 00 04 77 00 01 00 33 17 2E 22 73 01 00 01 02 58 00 FE                            22
    Remote_B+A4         00 05 50 94 64 1E 16 08 00 D5 9B 84 07 19 3C 3C 00 00 00 00 A4                               21    = 43    pos[41] = 0xA4

    Inverter            40 00 01 F8 00 04 77 00 01 00 33 17 2E 22 73 01 00 01 02 58 00 FF                            22
    Remote_B+Z0         00 05 50 94 64 1E 16 08 00 D5 9B 84 07 19 17 26 00 00 00 00 00                               21    = 43    pos[41] = 0x00

    Inverter            40 00 01 F8 00 04 77 00 01 00 33 17 2E 22 73 01 00 01 02 58 00 FF                            22
    Remote_B+80+81      00 05 50 94 64 1E 16 08 00 D5 9B 84 07 19 17 26 00 00 28 00 80 81 61 13 AF FF D2 12 4C 18 BB FF E9 FF FF 00 5E 0A 01 39 = 61 pos[42] = 0x80 
---------------------------------------------------------------------------------------------------------------------------------------------
    Buffer position     00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 41

'''
import serial
import time
import array
import argparse
import signal
import os

import paho.mqtt.client as mqtt #import the client1


def signal_handler(signal, frame):
    print('You pressed Ctrl+C!  Exiting...')
    print('')
    exit(0)

signal.signal(signal.SIGINT, signal_handler)

def safeDiv(x,y):
    try:
        return x/y
    except ZeroDivisionError:
        return 0

def printTable():
    global value_collection
    outarray={}
    arraylens={}
    maxarraylen=0
    _=os.system("clear")
    outline=[]
    outline.append([])
    for sectname in sorted(value_collection):
        for myfield,myval in sorted(value_collection[sectname].__dict__.items()):
            if(myfield!='decoded'):
                if(sectname not in outarray):
                    outarray[sectname]=[]
                    arraylens[sectname]=0
                    outline[0].append(sectname+":".ljust(17))
                mystr=str(myval)
                outarray[sectname].append(myfield+": "+mystr.rjust(15))
                arraylens[sectname]+=1
                if(arraylens[sectname]>maxarraylen):
                    maxarraylen=arraylens[sectname]

    for j in range(0,maxarraylen):
        outline.append([])
        for sectname in sorted(outarray):
            try:
                outline[j+1].append(outarray[sectname][j])
            except:
                outline[j+1].append("")

    cols=zip(*outline)
    col_widths=[ max(len(value) for value in col) for col in cols ]
    myformat = ' '.join(['%%%ds' % width for width in col_widths ])
    for row in outline:
        print(myformat % tuple(row))

def printSect(sectname):
    global value_collection
    outarray=[]
    for myfield,myval in sorted(value_collection[sectname].__dict__.items()):
        if(myfield!='decoded'):
            outarray.append('"'+myfield+'":"'+str(myval)+'"')
    print("{\""+sectname+"\": {"+",".join(outarray)+"}},")

def sendMQTT(sectname):
    global value_collection
    global mqttc
    global mqttClock
    global mqttOut
    global serial_port          # access to the global serial port argument:
    idx=serial_port[-1]

    retain=False
    if(mqttOut==2):
      retain=True
    outarray=[]
    currentClock=int(time.time())
    if(currentClock>mqttClock):
        for sectname in sorted(value_collection):
            for myfield,myval in sorted(value_collection[sectname].__dict__.items()):
                if(myfield!='decoded'):
                    mqttc.publish(sectname+idx+"/"+myfield,str(myval)+","+str(currentClock),retain=retain)
        mqttClock=currentClock

def sendOutput(sectname):
    global printOut
    global mqttOut
    if(printOut>0):
      printSect(sectname)
    if(mqttOut>0):
      sendMQTT(sectname)

class inverter_proto():
    """definition of inverter packet """
#    def __init__(self):
    status_descript = "NA"      #       status descriptive word:
    fault_descript = "NA"       #       fault descriptive word:
    model_descript = "NA"
    status_code = 0             # 0     packet_buffer[0]
    fault_code = 0              # 1     packet_buffer[1]
    volts_dc = 0.0              # 2     packet_buffer[2] HIGH BYTE
                                # 3     packet_buffer[3] LOW BYTE
    amps_dc = 0.0               # 4     packet_buffer[4] HIGH BYTE
                                # 5     packet_buffer[5] LOW BYTE
    volts_ac_out = 0            # 6     packet_buffer[6]
    volts_ac_in = 0             # 7     packet_buffer[7]
    LED_inverter = 0            # 8     packet_buffer[8]
    LED_charger = 0             # 9     packet_buffer[9]
    revision = 0.0              # 10    packet_buffer[10]
    temp_battery = 0            # 11    packet_buffer[11]
    temp_transformer = 0        # 12    packet_buffer[12]
    temp_FET = 0                # 13    packet_buffer[13]
    model_id = 0                # 14    packet_buffer[14]
    stack_mode = "NA"           # 15    packet_buffer[15]
    amps_ac_in = 0              # 16    packet_buffer[16]
    amps_ac_out = 0             # 17    packet_buffer[17]
    frequency_ac_out = 0.0      # 18    packet_buffer[18] HIGH BYTE
                                # 19    packet_buffer[19] LOW BYTE
#    ALWAYS 0                   # 20    packet_buffer[20]
#    ALWAYS 0xFF                # 21    packet_buffer[21]
#    END
#
#    inverter decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        self.decoded=1

        status_descriptions={0:"Charger Standby", 1:"Equalizing", 2:"Float Charging", 4:"Absorb Charging", 8:"Bulk Charging", 9:"Full Batt/Silent",
            10:"Load Support VDC", 11:"Load Support AAC", 16:"Charge", 32:"Off", 64:"Inverting", 80:"Standby", 96:"Searching"}
        self.status_code = packet_buffer[0]
        if (self.status_code in status_descriptions) :
            self.status_descript = status_descriptions[self.status_code]

        fault_descriptions={0:"No Faults", 1:"Stuck Relay", 2:"DC Overload", 3:"AC Overload", 4:"Dead Battery", 5: "AC Backfeed", 8:"Low Battery Cutout",
             9:"High Battery Cutout", 10:"High AC Output Volts", 16:"Bad FET Bridge", 18:"FETs Over Temperature", 19:"FETs Over Temperature Quick",
             20:"Internal Fault #4", 22:"Stacker Mode Fault", 23:"Stacker Sync Clock Lost", 24:"Stacker Sync Clock Out of Phase",
             25:"Stacker AC Phase Fault", 32:"Over Temperature Shutdown", 33:"Transfer Relay Fault", 128:"Charger Fault", 129:"Battery Temperature High",
             144:"Transformer Temperature Cutout Open", 145:"AC Breaker CB3 Tripped"}
        self.fault_code = packet_buffer[1]
        if (self.fault_code in fault_descriptions) :
            self.fault_descript = fault_descriptions[self.fault_code]

        self.volts_dc = round(((packet_buffer[2] * 256) + packet_buffer[3]) * 0.1,2)
        self.amps_dc = ((packet_buffer[4] * 256) + packet_buffer[5])
        if (self.amps_dc > 32768):
            self.amps_dc = (self.amps_dc-65536) + 0.0
        if (self.status_code==64):
            self.amps_dc *= -1
        self.volts_ac_out = packet_buffer[6]
        if (self.status_code==80):
            self.volts_ac_out=0
        self.volts_ac_in = packet_buffer[7]
        self.revision = round(packet_buffer[10] * 0.1,2)
        self.temp_battery = packet_buffer[11]
        self.temp_transformer = packet_buffer[12]
        self.temp_FET = packet_buffer[13]
        self.model_id = packet_buffer[14]
        if (self.model_id < 51):
            system_bus_volts = 12

        if (self.model_id > 50):
            system_bus_volts = 24

        if (self.model_id > 107):
            system_bus_volts = 48

        model_descriptions={ 6:"MM612",      7:"MM612-AE",    8:"MM1212",     9:"MMS1012",    10:"MM1012E",    11:"MM1512",  12:"MMS912E", 15:"ME1512",  20:"ME2012",
                            25:"ME2512",    30:"ME3112",     35:"MS2012",    40:"MS2012E",    45:"MS2812",     47:"MS2712E", 53:"MM1324E", 54:"MM1524",
                            55:"RD1824",    59:"RD2624E",    63:"RD2824",    69:"RD4024E",    74:"RD3924",     90:"MS4124E", 91:"MS2024", 103:"MSH4024M", 105:"MS4024",
                           106:"MS4024AE", 107:"MS4024PAE", 111:"MS4448AE", 112:"MS3748AEJ", 115:"MS4448PAE", 116:"MS3748PAEJ" }
        self.model_descript="Unknown"
        if (self.model_id in model_descriptions) :
            self.model_descript = model_descriptions[self.model_id]

        stack_modes={0:"Standalone Unit", 1:"Master in Parallel Stack", 2:"Slave in Parallel Stack", 4:"Master in Series Stack", 8:"Slave in Series Stack"}
        self.stack_mode_code = packet_buffer[15]
        if (self.stack_mode_code in stack_modes) :
            self.stack_mode = stack_modes[self.stack_mode_code]

        self.amps_ac_in = packet_buffer[16]
        if(self.amps_ac_in>128):
            self.amps_ac_in = (self.amps_ac_in-256)
        self.amps_ac_out = packet_buffer[17]
        if(self.amps_ac_out>128):
            self.amps_ac_out = (self.amps_ac_out-256)
        self.frequency_ac_out = ((packet_buffer[18] * 256) + packet_buffer[19]) * 0.1

class remote_base_proto():
    """definition of remote packet """
#    def __init__(self):
    status_code = 0             # 00    ord(packet_buffer[22])
    search_watts = 0.0          # 01    ord(packet_buffer[23])
    battery_size = 0.0          # 02    ord(packet_buffer[24])
    battery_type = 0.0          # 03    ord(packet_buffer[25])
    charger_amps = 0.0          # 04    ord(packet_buffer[26])
    shore_ac_amps = 0.0         # 05    ord(packet_buffer[27])
    revision = 0.0              # 06    ord(packet_buffer[28])
    parallel_threshold = 0      # 07    ord(packet_buffer[29]) LOW NIBBLE
    force_charge = 0            # 07    ord(packet_buffer[29]) HIGH NIBBLE
    genstart_auto = 0           # 08    ord(packet_buffer[30])
    battery_low_trip = 0.0      # 09    ord(packet_buffer[31])
    volts_ac_trip = 0           # 10    ord(packet_buffer[32])
    float_volts = 0.0           # 11    ord(packet_buffer[33])
    equalise_volts = 0.0        # 12    ord(packet_buffer[34])
    absorb_time = 0.0           # 13    ord(packet_buffer[35])
    absorb_volts = 14.4
    status_descript = "NA"
    battery_type_descript = "NA"
    force_charge_descript = "NA"
    genstart_auto_descript = "NA"
#    END
#
#    remote_base decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        self.decoded=1
        if (system_bus_volts == 24):
            self.absorb_volts *= 2

        if (system_bus_volts == 48):
            self.absorb_volts *= 4

        self.status_code = packet_buffer[22]
        if (self.status_code == '0x0') :
            self.status_descript = "Remote Command Clear"

        battery_descriptions={ 2:"Gel", 4:"Flooded", 8:"AGM", 10:"AGM2" }
        voltage_multiplier=(system_bus_volts/10)/10.0

        self.search_watts = packet_buffer[23]
        self.battery_size = packet_buffer[24] * 10
        self.battery_type = packet_buffer[25]
        self.battery_type_descript="Custom"
        if (self.battery_type in battery_descriptions):
            self.battery_type_descript = battery_descriptions[self.battery_type]

        if (self.battery_type_descript == "Custom"):
             self.absorb_volts=self.battery_type*voltage_multiplier

        self.charger_amps = packet_buffer[26]  # % of charger capacity
        self.shore_ac_amps = packet_buffer[27]
        self.revision = round(packet_buffer[28] * 0.1,2)
        self.parallel_threshold = (packet_buffer[29] & 0x0f) * 10
        self.force_charge = int(hex(packet_buffer[29] & 0xf0),16)
        force_charge_descriptions={ 16:"Disable Refloat", 32: "Force Silent", 64:"Force Float", 128:"Force Bulk"}
        if (self.force_charge in force_charge_descriptions):
            self.force_charge_descript = force_charge_descriptions[self.force_charge]

        genstart_auto_descriptions={0:"Off", 1:"Enable", 2:"Test", 4:"Enable with Quiet Time", 5:"On"}
        self.genstart_auto = packet_buffer[30]
        if (self.genstart_auto in genstart_auto_descriptions):
            self.genstart_auto_descript = genstart_auto_descriptions[self.genstart_auto]

        self.battery_low_trip = packet_buffer[31] * 0.1

        ac_trip_voltages={110:60, 122:65, 135:70, 145:75, 155:80, 165:85, 175:90, 182:95, 190:100, 192:"UPS Mode",255:"Ignore AC Input"}
        self.volts_ac_trip = packet_buffer[32]

        if (self.volts_ac_trip in ac_trip_voltages):
            self.volts_ac_trip = ac_trip_voltages[self.volts_ac_trip]

        self.float_volts = packet_buffer[33] * voltage_multiplier
        self.equalise_volts = packet_buffer[34] * voltage_multiplier

        self.absorb_time = packet_buffer[35] * 0.1                 # as decimal hours, 2.5 is 2 hours 30 minutes
        if(self.absorb_time==25.5):
            self.absorb_time=0.0

class remote_A0_proto():
    """definition of remote A0 packet """
#    def __init__(self):
    remote_hours = 0.0          # 14    ord(packet_buffer[36])
    remote_min = 0.0            # 15    ord(packet_buffer[37])
    ags_run_time = 0.0          # 16    ord(packet_buffer[38])
    ags_start_temp = 0.0        # 17    ord(packet_buffer[39])
    ags_volts_dc_start = 0.0    # 18    ord(packet_buffer[40])
    ags_quite_hours = 0         # 19    ord(packet_buffer[41])
#    FOOTER 0xA0                # 20    ord(packet_buffer[42])
#    END
#
#    remoteA0_agsA1 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        self.decoded=1
        voltage_multiplier = (system_bus_volts/10)/10.0

        self.remote_hours = packet_buffer[36]       # duplicate from BMK class
        self.remote_min = packet_buffer[37]         # duplicate from BMK class
        self.ags_run_time = packet_buffer[38] * 0.1
        self.ags_start_temp = packet_buffer[39]

        self.ags_volts_dc_start = round(packet_buffer[40] * voltage_multiplier,2)

        quiet_hours_descriptions={0:["Off",0,0], 1:["21h-07h",21,7], 2:["21h-08h",21,8], 3:["21h-09h",21,9], 4:["22h-08h",22,8], 5:["23h-08h",23,8]}
        self.ags_quiet_hours = packet_buffer[41]
        if (self.ags_quite_hours in quiet_hours_descriptions):
            self.ags_quiet_hours_descrip = quiet_hours_descriptions[self.ags_quiet_hours][0]
            self.ags_quiet_hours_start = quiet_hours_descriptions[self.ags_quiet_hours][1]
            self.ags_quiet_hours_end = quiet_hours_descriptions[self.ags_quiet_hours][2]


class AGS1_proto():
    """definition of remote A0 packet """
#    HEADER 0xA1                # 21    ord(packet_buffer[43])
    ags_status = 0              # 22    ord(packet_buffer[44])
    ags_revision = 0.0          # 23    ord(packet_buffer[45])
    ags_temperature = 0.0       # 24    ord(packet_buffer[46])
    ags_gen_runtime = 0.0       # 25    ord(packet_buffer[47])
    ags_volts_dc = 0.0          # 26    ord(packet_buffer[48])
    ags_quiet_hours_descrip = "NA"
    ags_status_descript = "NA"
#    END
#
#    agsA1 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        if(len(packet_buffer)<49):
            return
        self.decoded=1
        voltage_multiplier = (system_bus_volts/10)/10.0 # hack to drop the 1's position, then produce a float of just the 10's digit of the bus_volts
        ags_status_descriptions={0:"Non Valid", 1:"Off", 2:"Ready", 3:"Manual Run", 4:"Inverter in Charge Mode",
           5:"In Quiet Time", 6:"Start in Test Mode", 7:"Start on Temperature", 8:"Start on Voltage", 9:"Fault Start on Test",
           10:"Fault Start on Temperature", 11:"Fault Start on Voltage", 12:"Start Time of Day", 13:"Start State of Charge", 14:"Start Exercise",
           15:"Fault Start Time of Day", 16:"Fault Start State of Charge", 17:"Fault Start Exercise", 18:"Start on Amps", 19:"Start on Topoff",
           20:"Non Valid", 21:"Fault Start on Amps", 22:"Fault Start on Topoff", 23:"Non Valid", 24:"Fault Maximum Run",
           25:"Gen Run Fault", 26:"Generator in Warm Up", 27:"Generator in Cool Down"}
        self.ags_status = packet_buffer[44]
        if (self.ags_status in ags_status_descriptions):
            self.ags_status_descript = ags_status_descriptions[self.ags_status]

        self.ags_revision = round(packet_buffer[45] * 0.1,2)
        self.ags_temperature = packet_buffer[46]
        self.ags_run_time = packet_buffer[47] * 0.1

        self.ags_volts_dc = round(packet_buffer[48] * voltage_multiplier,2)

class remote_A1_proto():
    """definition of remote A1 packet """
#   def __init__(self):
    ags_start_time = 0.0        # 14    ord(packet_buffer[36])
    ags_stop_time = 0.0         # 15    ord(packet_buffer[37])
    ags_volts_dc_stop = 0.0     # 16    ord(packet_buffer[38])
    ags_start_delay = 0.0       # 17    ord(packet_buffer[39])
    ags_stop_delay = 0.0        # 18    ord(packet_buffer[40])
    ags_max_run_time = 0.0      # 19    ord(packet_buffer[41])
#   FOOTER 0xA1                 # 20    ord(packet_buffer[42])
#   remoteA1_agsA2 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        self.decoded=1
        voltage_multiplier = (system_bus_volts/10)*0.1

        self.ags_start_time = packet_buffer[36] * 0.25
        self.ags_stop_time = packet_buffer[37] * 0.25

        if (packet_buffer[36] == packet_buffer[37]):
            self.ags_start_stop_enable = "Disabled"
        else:
            self.ags_start_stop_enable = "Enabled"

        self.ags_volts_dc_stop = round(packet_buffer[38] * voltage_multiplier,2)

        if (packet_buffer[39] & 0x80):                                  # check for minutes selection as MSB:
            self.ags_start_delay = (packet_buffer[39] & 0x7f) * 60      # strip MSB and store as seconds
        else:
            self.ags_start_delay = packet_buffer[39]                    # store seconds

        if (packet_buffer[40] & 0x80):                                  # check for minutes selection as MSB:
            self.ags_stop_delay = (packet_buffer[40] & 0x7f) * 60       # strip MSB and store as seconds
        else:
            self.ags_stop_delay = packet_buffer[40]                     # store seconds

        self.ags_max_run_time = packet_buffer[41] * 0.1


class AGS2_proto():
    """definition of remote A1 packet """
#    def __init__(self):
#    HEADER 0xA2                 # 21    ord(packet_buffer[43])
    ags_days_last_gen_run = 0    # 22    ord(packet_buffer[44])
    ags_days_since_full_soc =  0 # 23    ord(packet_buffer[45])
    ags_gen_runtime = 0          # 24    ord(packet_buffer[46]) # High byte
                                 # 25    ord(packet_buffer[47]) # Low byte
#    ALWAYS 0                    # 26    ord(packet_buffer[48])
    ags_start_stop_enable = "NA"
#    END
#
#    remoteA1_agsA2 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        if(len(packet_buffer)<49):
            return
        self.decoded=1
        self.ags_days_last_gen_run = packet_buffer[44]
        self.ags_days_since_full_soc = packet_buffer[45]
        self.ags_gen_runtime = (packet_buffer[46]*256)+packet_buffer[47]

class remote_A2_proto():
    """definition of remote A2 packet """
#    def __init__(self):
    ags_soc_start = 0           # 14    ord(packet_buffer[36])
    ags_soc_stop = 0            # 15    ord(packet_buffer[37])
    ags_amps_start = 0          # 16    ord(packet_buffer[38])
    ags_amps_start_delay = 0    # 17    ord(packet_buffer[39])
    ags_amps_stop = 0           # 18    ord(packet_buffer[40])
    ags_amps_stop_delay = 0     # 19    ord(packet_buffer[41])
#    FOOTER 0xA2                # 20    ord(packet_buffer[42])
#    END
#
#    remote_A2 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        self.decoded=1

        self.ags_soc_start = packet_buffer[36]
        self.ags_soc_stop = packet_buffer[37]
        self.ags_amps_start = packet_buffer[38]

        if (packet_buffer[39] & 0x80):                                          # check for minutes selection as MSB:
            self.ags_amps_start_delay = (packet_buffer[39] & 0x7f) * 60         # strip MSB and store as seconds
        else:
            self.ags_amps_start_delay = packet_buffer[39]                       # store seconds

        self.ags_amps_stop = packet_buffer[40]

        if (packet_buffer[41] & 0x80):                                          # check for minutes selection as MSB:
            self.ags_amps_stop_delay = (packet_buffer[41] & 0x7f) * 60          # strip MSB and store as seconds
        else:
            self.ags_amps_stop_delay = packet_buffer[41]                        # store seconds

class remote_A3_proto():
    """definition of remote A3 packet """
#    def __init__(self):
    ags_quite_time_start = 0.0  # 14    ord(packet_buffer[36])
    ags_quite_time_stop = 0.0   # 15    ord(packet_buffer[37])
    ags_exercise_days = 0       # 16    ord(packet_buffer[38])
    ags_exercise_start_time = 0.0 # 17  ord(packet_buffer[39])
    ags_exercise_run_time = 0   # 18    ord(packet_buffer[40])
    ags_top_off = 0             # 19    ord(packet_buffer[41])
#    FOOTER 0xA3                # 20    ord(packet_buffer[42])
#    END
#
#    remoteA3 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        self.decoded=1
        self.ags_quite_time_start = packet_buffer[36] * 0.25
        self.ags_quite_time_stop = packet_buffer[37] * 0.25
        self.ags_exercise_days = packet_buffer[38]
        self.ags_exercise_start_time = packet_buffer[39] * 0.25
        self.ags_exercise_run_time = packet_buffer[40] * 0.1
        self.ags_top_off = packet_buffer[41]

class remote_A4_proto():
    """definition of remote A4 packet """
#    def __init__(self):
    ags_warm_up_time = 0        # 14    ord(packet_buffer[36])
    ags_cool_down_time = 0      # 15    ord(packet_buffer[37])
#     ALWAYS 0                  # 16    ord(packet_buffer[38])
#     ALWAYS 0                  # 17    ord(packet_buffer[39])
#     ALWAYS 0                  # 18    ord(packet_buffer[40])
#     ALWAYS 0                  # 19    ord(packet_buffer[41])
#    FOOTER 0xA4                # 20    ord(packet_buffer[42])
#    END
#
#    remoteA4 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        self.decoded=1

        if (packet_buffer[36] & 0x80):                                          # check for minutes selection as MSB:
            self.ags_warm_up_time = (packet_buffer[36] & 0x7f) * 60             # strip MSB and store as seconds
        else:
            self.ags_warm_up_time = packet_buffer[36]                           # store seconds

        if (packet_buffer[37] & 0x80):                                          # check for minutes selection as MSB:
            self.ags_cool_down_time = (packet_buffer[37] & 0x7f) * 60           # strip MSB and store as seconds
        else:
            self.ags_cool_down_time = packet_buffer[37]                         # store seconds

class remote_C0_proto():
    """definition of remote C0 packet """
#    def __init__(self):
    pt_force_charge = 0         # 14    ord(packet_buffer[36])
    pt_relay_state = 0          # 15    ord(packet_buffer[37]) # bits 0,1
    pt_buzzer_state = 0         # 15    ord(packet_buffer[37]) # bits 2,3
#    EMTPY 0                     # 15    ord(packet_buffer[37]) # bits 4-7
    pt_resets = 0               # 16    ord(packet_buffer[38])
    pt_unit_num = 0             # 17    ord(packet_buffer[39]) # bits 0-2
    pt_packet_num = 0           # 17    ord(packet_buffer[39]) # bits 3-7
    pt_log_num = 0              # 18    ord(packet_buffer[40]) # 9 bits
                                 # 19    ord(packet_buffer[41])
#    FOOTER 0xC0                 # 20    ord(packet_buffer[42])
#    END
#
#    remoteC0 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        self.decoded=1
        pt_force_charge_descriptions={0:"Multistage", 1:"Off", 2:"Force Float", 3:"Force Bulk", 4:"Equalize"}
        self.pt_force_charge=packet_buffer[36]
        if(self.pt_force_charge in pt_force_charge_descriptions):
           self.pt_force_charge_descript=pt_force_charge_descriptions[self.pt_force_charge]
        self.pt_relay_state = packet_buffer[37] & 0xfc
        self.pt_buzzer_state = packet_buffer[37] & 0xf3
        self.pt_resets = packet_buffer[38]

class remote_C1_proto():
    """definition of remote C1 packet """
#    def __init__(self):
    pt_relay_on_vdc = 0.0       # 14    ord(packet_buffer[36])
    pt_relay_off_vdc = 0.0      # 15    ord(packet_buffer[37])
    pt_relay_on_delay = 0.0     # 16    ord(packet_buffer[38])
    pt_relay_off_delay = 0.0    # 17    ord(packet_buffer[39])
    pt_batt_temp_comp = 0.0     # 18    ord(packet_buffer[40])
    pt_power_save_time = 0      # 19    ord(packet_buffer[41])
#    FOOTER 0xC1                 # 20    ord(packet_buffer[42])
#    END
#
#    remoteC1 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        voltage_multiplier = (system_bus_volts/10)*0.1
        self.decoded=1
        self.pt_relay_on_vdc=packet_buffer[36]*voltage_multiplier
        self.pt_relay_off_vdc=packet_buffer[37]*voltage_multiplier
        if (packet_buffer[38] & 0x80):                                          # check for minutes selection as MSB:
            self.pt_relay_on_delay = (packet_buffer[38] & 0x7f) * 60            # strip MSB and store as seconds
        else:
            self.pt_relay_on_delay = packet_buffer[38]                           # store seconds

        if (packet_buffer[39] & 0x80):                                          # check for minutes selection as MSB:
            self.pt_relay_off_delay = (packet_buffer[39] & 0x7f) * 60           # strip MSB and store as seconds
        else:
            self.pt_relay_off_delay = packet_buffer[39]                         # store seconds
        self.pt_batt_temp_comp = packet_buffer[40]
        self.pt_power_save_time = packet_buffer[41]

class remote_C2_proto():
    """definition of remote C2 packet """
#    def __init__(self):
    pt_alarm_on_vdc = 0.0       # 14    ord(packet_buffer[36])
    pt_alarm_off_vdc = 0.0      # 15    ord(packet_buffer[37])
    pt_alarm_on_delay = 0.0     # 16    ord(packet_buffer[38])
    pt_alarm_off_delay = 0.0    # 17    ord(packet_buffer[39])
    pt_eq_done_timer = 0.0      # 18    ord(packet_buffer[40])
    pt_charge_rate = 0          # 19    ord(packet_buffer[41]) #bits 0-7
    pt_rebulk_on_sunup = 0      # 19    ord(packet_buffer[41]) #bits 8
#    FOOTER 0xC2                 # 20    ord(packet_buffer[42])
#    END
#
#    remoteC2 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        voltage_multiplier = (system_bus_volts/10)*0.1
        self.decoded=1
        self.pt_alarm_on_vdc=packet_buffer[36]*voltage_multiplier
        self.pt_alarm_off_vdc=packet_buffer[37]*voltage_multiplier
        if (packet_buffer[38] & 0x80):                                          # check for minutes selection as MSB:
            self.pt_alarm_on_delay = (packet_buffer[38] & 0x7f) * 60            # strip MSB and store as seconds
        else:
            self.pt_alarm_on_delay = packet_buffer[38]                           # store seconds

        if (packet_buffer[39] & 0x80):                                          # check for minutes selection as MSB:
            self.pt_alarm_off_delay = (packet_buffer[39] & 0x7f) * 60           # strip MSB and store as seconds
        else:
            self.pt_alarm_off_delay = packet_buffer[39]                         # store seconds
        self.pt_eq_done_timer = packet_buffer[40]
        self.pt_charge_rate = packet_buffer[41] & 0x7F
        self.pt_rebulk_on_sunup = packet_buffer[41] & 0x80

class remote_C3_proto():
    """definition of remote C3 packet """
#    def __init__(self):
    pt_absorb_vdc = 0.0         # 14    ord(packet_buffer[36])
    pt_float_vdc = 0.0          # 15    ord(packet_buffer[37])
    pt_equalize_vdc = 0.0       # 16    ord(packet_buffer[38])
    pt_absorb_time = 0.0        # 17    ord(packet_buffer[39])
    pt_rebulk_vdc = 0.0         # 18    ord(packet_buffer[40])
    pt_batt_temp_comp = 0.0     # 19    ord(packet_buffer[41])
#    FOOTER 0xC3                 # 20    ord(packet_buffer[42])
#    END
#
#    remoteC3 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        voltage_multiplier = (system_bus_volts/10)*0.1
        self.decoded=1
        self.pt_absorb_vdc = packet_buffer[36]*voltage_multiplier
        self.pt_float_vdc = packet_buffer[37]*voltage_multiplier
        self.pt_equalize_vdc = packet_buffer[38]*voltage_multiplier
        if (packet_buffer[39] & 0x80):                                          # check for minutes selection as MSB:
            self.pt_absorb_time = (packet_buffer[39] & 0x7f) * 60            # strip MSB and store as seconds
        else:
            self.pt_absorb_time = packet_buffer[39]                           # store seconds
        self.pt_rebulk_vdc = packet_buffer[40]
        self.pt_batt_temp_comp = packet_buffer[41]

class PT1_proto():
    """definition of PT100 C1 packet """
#    HEADER 0xC1               # 21    ord(packet_buffer[43])
    pt_address = 0             # 22    ord(packet_buffer[44]) # bits 0-2
    pt_onoff = 0               # 23    ord(packet_buffer[45]) # bit 0
    pt_mode = 0                # 23    ord(packet_buffer[45]) # bit 1-3
    pt_status = 0              # 23    ord(packet_buffer[45]) # High nibble
    pt_fault_code = 0          # 24    ord(packet_buffer[46])
    pt_batt_volts_dc = 0.0     # 25    ord(packet_buffer[47]) # High Byte
                               # 26    ord(packet_buffer[48]) # Low Byte
    pt_batt_amps_dc = 0.0      # 27    ord(packet_buffer[49]) # High Byte
                               # 28    ord(packet_buffer[50]) # Low Byte
    pt_pv_volts_dc = 0.0       # 29    ord(packet_buffer[51]) # High Byte
                               # 30    ord(packet_buffer[52]) # Low Byte
    pt_charge_time = 0         # 31    ord(packet_buffer[53])
    pt_target_batt_vdc = 0     # 32    ord(packet_buffer[54])
    pt_relay_state = 0         # 33    ord(packet_buffer[55]) # bit 0
    pt_alarm_state = 0         # 33    ord(packet_buffer[55]) # bit 1

    pt_battery_temp = 0        # 34    ord(packet_buffer[56])
    pt_inductor_temp = 0       # 35    ord(packet_buffer[57])
    pt_fet_temp = 0            # 36    ord(packet_buffer[58])
    pt_status_descript = "NA"
    pt_mode_descript = "NA"
    pt_fault_descript = "NA"
#    END
#
#    pt100_c1 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        if(len(packet_buffer)<59):
            return
        self.decoded=1

        voltage_multiplier=(system_bus_volts/10)/10.0

        self.pt_status_descript = "NA"
        self.pt_mode_descript = "NA"
        self.pt_fault_descript = "NA"

        pt100_fault_descriptions={0:"No Fault", 1: "No PV Input Fault", 2: "Internal PSU Fault", 3: "High PV Input Fault",
                4: "High Battery Fault", 5: "BTS Shorted Fault", 6: "FET Overtemp Fault", 7: "High Battery Temp Fault",
                8: "Internal Overload Fault", 9: "Internal Phase Fault", 10: "BTS Open Fault", 11: "Internal Power Fault",
               12: "GFDI Fault", 13: "AFP Fault (Arc Fault)", 14: "Internal NTC Fault (Neg Temp Coef)",
               15: "Internal Hardware Fault", 16: "Inductor Overtemp Fault", 17: "USB Fault", 20: "No Stack Comm (DIP 10 Up)",
               21: "Stack Comm Lost", 22: "Stack Switch", 23: "Battery Volts (delta on multiple PT100s)"}

        pt100_status_descriptions={0:"Sleeping",1:"Regulating: VDC", 2:"Regulating: ADC", 3:"Limit: Int Temp",
               4:"Limit: Int Hz", 5:"Limit: Above VDC",15:"MPPT On"}

        pt100_mode_descriptions={0:"Float", 2:"Bulk", 3:"Absorb", 4:"Equalize", 5:"Float"}

        # From 7-13 Protcol Spec -- Doesn't seem to accurate
        # pt100_mode_descriptions={0:"Unknown", 2:"Sleep", 3:"Float", 4:"Bulk", 5:"Absorb", 6:"Equalize"}

        self.pt_address = packet_buffer[44]
        self.pt_onoff = packet_buffer[45] & 0x01
        self.pt_status = int(hex(packet_buffer[45] & 0xf0),16)/16
        self.pt_mode = packet_buffer[45] & 0x0e

        if(self.pt_status in pt100_status_descriptions):
            self.pt_status_descript=pt100_status_descriptions[self.pt_status]

        if(self.pt_mode in pt100_mode_descriptions):
            self.pt_mode_descript=pt100_mode_descriptions[self.pt_mode]

        if(self.pt_status==0):
            self.pt_mode_descript="Off"

        self.pt_fault_code = packet_buffer[46]
        self.pt_batt_volts_dc = round(((packet_buffer[47]*256)+packet_buffer[48])*0.1,2)
        self.pt_batt_amps_dc = round(((packet_buffer[49]*256)+packet_buffer[50])*0.1,2)
        self.pt_pv_volts_dc = round(((packet_buffer[51]*256)+packet_buffer[52])*0.1,2)
        self.pt_charge_time = packet_buffer[53] * 0.1
        self.pt_target_batt_vdc = round(packet_buffer[54] * voltage_multiplier,2)
        self.pt_relay_state = packet_buffer[55] & 0x01
        self.pt_alarm_state = (packet_buffer[55] & 0x02)/2
        self.pt_battery_temp = packet_buffer[56]
        self.pt_inductor_temp = packet_buffer[57]
        self.pt_fet_temp = packet_buffer[58]
        if(self.pt_fault_code in pt100_fault_descriptions):
            self.pt_fault_descript=pt100_fault_descriptions[self.pt_fault_code]

class PT2_proto():
    """definition of PT100 C2 packet """
#    HEADER 0xC2               # 21    ord(packet_buffer[43])
    pt_address = 0             # 22    ord(packet_buffer[44]) # Low 3 bits
    pt_kwh_lifetime = 0        # 23    ord(packet_buffer[45]) # High byte
                               # 24    ord(packet_buffer[46]) # Low byte * 0.01
                               # 25    ord(packet_buffer[47]) # Observed: 1
    pt_kwh_resettable = 0      # 26    ord(packet_buffer[48]) # * 0.1
    pt_ground_fault_adc = 0    # 27    ord(packet_buffer[49]) # * 0.01
                               # 28    ord(packet_buffer[50]) # Observed: 1
    pt_nom_batt_vdc = 0        # 29    ord(packet_buffer[51]) # Bit 0-5 & 0x3F ( Observed: 0 )
    pt_stack_info = 0          # 29    ord(packet_buffer[51]) # Bit 6,7 & 0xC0 ( Observed: 0 )
    pt_revision = 0.0          # 30    ord(packet_buffer[52])/10
    pt_model = 0               # 31    ord(packet_buffer[53]) # 
    pt_out_adc_rating = 0      # 32    ord(packet_buffer[54]) # 
    pt_in_vdc_rating = 0       # 33    ord(packet_buffer[55]) # 
#    END
#
#    pt100_c2 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        if(len(packet_buffer)<56):
            return
        self.decoded=1

        self.pt_byte42 = packet_buffer[44]
        self.pt_kwh_lifetime = ((packet_buffer[45]*256)+packet_buffer[46])*10
        self.pt_byte45 = packet_buffer[47]
        self.pt_kwh_resettable = packet_buffer[48]*0.1
        self.pt_ground_fault_adc = packet_buffer[49]*0.01
        self.pt_byte48 = packet_buffer[50]
        self.pt_byte49 = packet_buffer[51]
        self.pt_revision = round(packet_buffer[52]*0.1,2)
        self.pt_model = packet_buffer[53]
        self.pt_out_adc_rating = packet_buffer[54] * 5
        self.pt_in_vdc_rating = packet_buffer[55] * 10

class PT3_proto():
    """definition of PT100 C3 packet """
#    HEADER 0xC3               # 21    ord(packet_buffer[43])
    pt_byte44 = 0              # 24    ord(packet_buffer[44]) # Unknown, observed value: 0
    pt_byte45 = 0              # 25    ord(packet_buffer[45]) # Unknown, observed value: 13
    pt_byte46 = 0              # 26    ord(packet_buffer[46]) # Unknown, observed value: 126
    pt_byte47 = 0              # 27    ord(packet_buffer[47]) # Unknown, observed value: 69
    pt_byte48 = 0              # 28    ord(packet_buffer[48]) # Unknown, observed value: 122
    pt_byte49 = 0              # 29    ord(packet_buffer[49]) # Unknown, observed value: 89
    pt_byte50 = 0              # 30    ord(packet_buffer[50]) # Unknown, observed value: 118
    pt_byte51 = 0              # 31    ord(packet_buffer[51]) # Unknown, observed value: 55
    pt_byte52 = 0              # 32    ord(packet_buffer[52]) # Unknown, observed value: 34
    pt_byte53 = 0              # 33    ord(packet_buffer[53]) # Unknown, observed value: 5
    pt_byte54 = 0              # 34    ord(packet_buffer[54]) # Unknown, observed value: 9
    pt_byte55 = 0              # 35    ord(packet_buffer[55]) # Unknown, observed value: 90
    pt_byte56 = 0              # 36    ord(packet_buffer[56]) # Unknown, observed value: 9
    pt_byte57 = 0              # 37    ord(packet_buffer[57]) # Unknown, observed value: 90
#    END
#
#    pt100_c3 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        if(len(packet_buffer)<58):
            return
        self.decoded=1

        self.pt_byte44 = packet_buffer[44]
        self.pt_byte45 = packet_buffer[45]
        self.pt_byte46 = packet_buffer[46]
        self.pt_byte47 = packet_buffer[47]
        self.pt_byte48 = packet_buffer[48]
        self.pt_byte49 = packet_buffer[49]
        self.pt_byte50 = packet_buffer[50]
        self.pt_byte51 = packet_buffer[51]
        self.pt_byte52 = packet_buffer[52]
        self.pt_byte53 = packet_buffer[53]
        self.pt_byte54 = packet_buffer[54]
        self.pt_byte55 = packet_buffer[55]
        self.pt_byte56 = packet_buffer[56]
        self.pt_byte57 = packet_buffer[57]


class PT4_proto():
    """definition of PT100 C4 packet """
#    HEADER 0xC4               # 21    ord(packet_buffer[43])
    pt_byte44 = 0              # 24    ord(packet_buffer[44]) # Unknown
    pt_byte45 = 0              # 25    ord(packet_buffer[45]) # Unknown
    pt_byte46 = 0              # 26    ord(packet_buffer[46]) # Unknown
    pt_byte47 = 0              # 27    ord(packet_buffer[47]) # Unknown
    pt_byte48 = 0              # 28    ord(packet_buffer[48]) # Unknown
    pt_byte49 = 0              # 29    ord(packet_buffer[49]) # Unknown
    pt_byte50 = 0              # 30    ord(packet_buffer[50]) # Unknown
#    END
#
#    pt100_c4 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        if(len(packet_buffer)<51):
            return
        self.decoded=1

        self.pt_byte44 = packet_buffer[44]
        self.pt_byte45 = packet_buffer[45]
        self.pt_byte46 = packet_buffer[46]
        self.pt_byte47 = packet_buffer[47]
        self.pt_byte48 = packet_buffer[48]
        self.pt_byte49 = packet_buffer[49]
        self.pt_byte50 = packet_buffer[50]

class RTR_proto():
    """definition of remote A2 packet """
#    def __init__(self):
#    HEADER 0x91                # 21    ord(packet_buffer[43])
    rtr_revision = 0            # 22    ord(packet_buffer[44])
#    END
#
#    remoteA2_RTR decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        self.decoded=1

        self.rtr_revision = round(packet_buffer[44] * 0.1,2)

class remote_11_proto():
    """definition of remote Z0 packet """
#    def __init__(self):
    shore_amps = 0              # 14    ord(packet_buffer[36])
    vac_cutout_in2 = 0          # 15    ord(packet_buffer[37])
#     ALWAYS 0                  # 16    ord(packet_buffer[38])
#     ALWAYS 0                  # 17    ord(packet_buffer[39])
#     ALWAYS 0                  # 18    ord(packet_buffer[40])
#     ALWAYS 0                  # 19    ord(packet_buffer[41])
#     ALWAYS 0                  # 20    ord(packet_buffer[42])
#    END
#
#    remote_11 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        self.decoded=1
        self.shore_amps = packet_buffer[36]
        self.vac_cutout_in2 = packet_buffer[37]
#        nothing to do here, move along:

class remote_Z0_proto():
    """definition of remote Z0 packet """
#    def __init__(self):
    remote_hours = 0            # 14    ord(packet_buffer[36])
    remote_min = 0              # 15    ord(packet_buffer[37])
#     ALWAYS 0                  # 16    ord(packet_buffer[38])
#     ALWAYS 0                  # 17    ord(packet_buffer[39])
#     ALWAYS 0                  # 18    ord(packet_buffer[40])
#     ALWAYS 0                  # 19    ord(packet_buffer[41])
#     ALWAYS 0                  # 20    ord(packet_buffer[42])
#    END
#
#    remote_Z0 decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        self.decoded=1
        self.remote_hours=packet_buffer[36]
        self.remote_min=packet_buffer[37]
#        nothing to do here, move along:

class remote_BMK_proto():
    """definition of remote BMK packet """
#    def __init__(self):
    remote_hours = 0            # 14    ord(packet_buffer[36])
    remote_min = 0              # 15    ord(packet_buffer[37])
    bmk_battery_efficiency = 0  # 16    ord(packet_buffer[38])
    bmk_resets = 0              # 17    ord(packet_buffer[39])
    bmk_battery_size = 0        # 18    ord(packet_buffer[40])
#    ALWAYS 0                   # 19    ord(packet_buffer[41])
#    FOOTER 0x80                # 20    ord(packet_buffer[42])
    bmk_resets_descript="NA"
#    END
#
#    remote_BMK decode function:
    decoded=1
    def decode(self, packet_buffer):
        global system_bus_volts
        self.decoded=1

        bmk_resets_descriptions={0:"Normal Running", 1:"Reset min VDC", 2:"Reset max VDC", 3: "Reset Amp Hour Trip", 4: "Reset kAmp Hours"}

        self.remote_hours = packet_buffer[36]
        self.remote_min = packet_buffer[37]
        self.bmk_battery_efficiency = packet_buffer[38]
        self.bmk_resets = packet_buffer[39]
        if(self.bmk_resets in bmk_resets_descriptions):
          self.bmk_resets_descript=bmk_resets_descriptions[self.bmk_resets]
        self.bmk_battery_size = packet_buffer[40] * 10

class BMK_proto():
    """definition of remote BMK packet """
#    def __init__(self):
#    HEADER 0x81                # 21    ord(packet_buffer[43])
    bmk_soc = 0                 # 22    ord(packet_buffer[44])
    bmk_volts_dc = 0.0          # 23    ord(packet_buffer[45]) HIGH BYTE
                                # 24    ord(packet_buffer[46]) LOW  BYTE
    bmk_amps_dc = 0.0           # 25    ord(packet_buffer[47]) HIGH BYTE
                                # 26    ord(packet_buffer[48]) LOW  BYTE 
    bmk_volts_min = 0.0         # 27    ord(packet_buffer[49]) HIGH BYTE
                                # 28    ord(packet_buffer[50]) LOW  BYTE
    bmk_volts_max = 0.0         # 29    ord(packet_buffer[51]) HIGH BYTE
                                # 30    ord(packet_buffer[52]) LOW  BYTE
    bmk_amp_hour_net = 0.0      # 31    ord(packet_buffer[53]) HIGH BYTE
                                # 32    ord(packet_buffer[54]) LOW  BYTE
    bmk_amp_hour_trip = 0       # 33    ord(packet_buffer[55]) HIGH BYTE
                                # 34    ord(packet_buffer[56]) LOW  BYTE
    bmk_amp_hour_total = 0      # 35    ord(packet_buffer[57]) HIGH BYTE
                                # 36    ord(packet_buffer[58]) LOW  BYTE
    bmk_revision = 0.0          # 37    ord(packet_buffer[59])
    bmk_fault = 0               # 38    ord(packet_buffer[60])
    bmk_fault_descrip = "NA"
#    END
#
#    remote_BMK decode function:
    decoded=0
    def __getitem__(self, item):
        return getattr(self, item)
    def decode(self, packet_buffer):
        global system_bus_volts
        if(len(packet_buffer)<61):
            return
        self.decoded=1

        self.bmk_battery_soc = packet_buffer[44]
        self.bmk_volts_dc = round(((packet_buffer[45] * 256) + packet_buffer[46]) * 0.01,2)
        self.bmk_amps_dc = (packet_buffer[47] * 256) + packet_buffer[48] + 0.0
        if (self.bmk_amps_dc > 32768):
            self.bmk_amps_dc = (self.bmk_amps_dc-65536) + 0.0

        self.bmk_amps_dc = self.bmk_amps_dc * 0.1

        self.bmk_volts_min = ((packet_buffer[49] * 256) + packet_buffer[50]) * 0.01
        self.bmk_volts_max = ((packet_buffer[51] * 256) + packet_buffer[52]) * 0.01

        self.bmk_amp_hour_net = (packet_buffer[53] * 256) + packet_buffer[54] + 0.0
        if (self.bmk_amp_hour_net > 32768):
            self.bmk_amp_hour_net = self.bmk_amp_hour_net - 65536

        self.bmk_amp_hour_trip = ((packet_buffer[55] * 256) + packet_buffer[56]) * 0.1
        self.bmk_amp_hour_total = ((packet_buffer[57] * 256) + packet_buffer[58]) * 100

        self.bmk_revision = round(packet_buffer[59] * 0.1,2)
        self.bmk_fault = packet_buffer[60]
        bmk_fault_descriptions={0:"Reserved", 1:"No Faults", 2:"Fault Start"}
        if (self.bmk_fault in bmk_fault_descriptions):
            self.bmk_fault_descrip = bmk_fault_descriptions[self.bmk_fault]

# main application function:
def main():
    value_collection['inverter'] = inverter_proto()
    value_collection['remote_base'] = remote_base_proto()
    value_collection['remote_11'] = remote_11_proto()
    value_collection['remote_A0'] = remote_A0_proto()
    value_collection['remote_A1'] = remote_A1_proto()
    value_collection['remote_A2'] = remote_A2_proto()
    value_collection['remote_A3'] = remote_A3_proto()
    value_collection['remote_A4'] = remote_A4_proto()
    value_collection['remote_C0'] = remote_C0_proto()
    value_collection['remote_Z0'] = remote_Z0_proto()
    value_collection['remote_BMK'] = remote_BMK_proto()
    value_collection['BMK']  = BMK_proto()    
    value_collection['RTR']  = RTR_proto()
    value_collection['AGS1'] = AGS1_proto()
    value_collection['AGS2'] = AGS2_proto()
    value_collection['PT1'] = PT1_proto()
    value_collection['PT2'] = PT2_proto()
    value_collection['PT3'] = PT3_proto()
    global serial_port          # access to the global serial port argument:
    global printTables

#    open commuication port:
    def openPort(serial_port):
        try:
            mag_port = serial.Serial(port = serial_port,
                            baudrate = 19200,
                            bytesize = 8,
                            timeout = None)

            return(mag_port)
        except:
            print('Error: Failed to open commuications port, exiting')
            exit()

#    main application loop:
    def mainLoop():
        while (True):
            serial_byte     = 0
            sync_locked     = 0
            serial_buffer   = array.array('i')

            # call to open the communications port and assign handle on success:
            mag_port = openPort(serial_port)

            mag_port.read(100)
            mag_port.flush()

            sync_locked = 0
            bytes_waiting = 0

            while (sync_locked < 0.03):
                sync_check_start = time.time()
  
                try:
                    serial_byte = mag_port.read(1)
  
                except:
                    print()
                    print("Error: Failed to read communications Port, exiting")
                    mag_port.close()
                    exit()
  
                sync_check_stop = time.time()
                sync_locked = sync_check_stop - sync_check_start
  
            if debug_level > 0:
                print()
                print("sync")

                print("     |{0:65s}|{1:41s}|{2:20s}|{3:s}".format("Inverter","Remote","Remote Acc","Accessory"))
                print("     ",end="")
                for i in range(0,62):#bytes_waiting -1):
                    print("{0:02d} ".format(i),end="",flush=True)
                print()

            maxP=8
            for p in range(0,maxP):

                time.sleep(0.07)

                bytes_waiting = mag_port.inWaiting()

                serial_buffer = b"".join([serial_byte, mag_port.read(bytes_waiting)])
                #newbuf=serial_buffer
                #serial_buffer=newbuf[:20]+newbuf[22:]
                #del newbuf

                if debug_level > 0:
                    print("({0:02d}) ".format(bytes_waiting+1),end="",flush=True)

                    for i in range(0,bytes_waiting+1):
                        print("{0:02x} ".format(serial_buffer[i]),end="",flush=True)
                    print()

                # Check if we have a remote connected and decode it, otherwise program fails
                if (len(serial_buffer) > 20):
                    if(len(serial_buffer) > 42): # We have a remote protocol packet
                    #if(True): # We have a remote protocol packet
                        if (serial_buffer[42] == 0xa0):
                            if debug_level > 0:
                                print("Remote A0 Packet ")
                            value_collection['remote_A0'].decode(serial_buffer)
                            sendOutput('remote_A0')
    
                        elif (serial_buffer[42] == 0x11):
                            if debug_level > 0:
                                print("Remote 11 Packet")
                            value_collection['remote_11'].decode(serial_buffer)
                            sendOutput('remote_11')
    
                        elif (serial_buffer[42] == 0xa1):
                            if debug_level > 0:
                                print("Remote A1 Packet")
                            value_collection['remote_A1'].decode(serial_buffer)
                            sendOutput('remote_A1')
    
                        elif (serial_buffer[42] == 0xa2):
                            if debug_level > 0:
                                print("Remote A2 Packet")
                            value_collection['remote_A2'].decode(serial_buffer)
                            sendOutput('remote_A2')
    
                        elif (serial_buffer[42] == 0xa3):
                            if debug_level > 0:
                                print("Remote A3 Packet")
                            value_collection['remote_A3'].decode(serial_buffer)
                            sendOutput('remote_A3')
    
                        elif (serial_buffer[42] == 0xa4):
                            if debug_level > 0:
                                print("Remote A4 Packet")
                            value_collection['remote_A4'].decode(serial_buffer)
                            sendOutput('remote_A4')
    
                        elif (serial_buffer[42] == 0xc0):
                            if debug_level > 0:
                                print("Remote C1 Packet")
                            value_collection['remote_C0'].decode(serial_buffer)
                            sendOutput('remote_C0')

                        #elif (serial_buffer[42] == 0x11):
    
                        elif (serial_buffer[42] == 0x00):
                            if debug_level > 0:
                                print("Remote Z0 Packet")
                            value_collection['remote_Z0'].decode(serial_buffer)
                            # sendOutput('remote_Z0')  # Nothing really to print here... ignore it
    
                        elif (serial_buffer[42] == 0x80):
                            if debug_level > 0:
                                print("Remote BMK Packet")
                            value_collection['remote_BMK'].decode(serial_buffer)
                            sendOutput('remote_BMK')

                    # decode if an accesory responded 
                    if(len(serial_buffer)>43):
#                        if debug_level > 0:
#                            print("Decoding Accessory")
    
                        if (serial_buffer[43] == 0x81):
                            if debug_level > 0:
                                print("BMK Packet")
                            value_collection['BMK'].decode(serial_buffer)
                            sendOutput('BMK')
    
                        elif (serial_buffer[43] == 0x91):
                            if debug_level > 0:
                                print("RTR Packet")
                            value_collection['RTR'].decode(serial_buffer)
                            sendOutput('RTR')
    
                        elif (serial_buffer[43] == 0xA1):
                            if debug_level > 0:
                                print("AGS1 Packet")
                            value_collection['AGS1'].decode(serial_buffer)              
                            sendOutput('AGS1')
    
                        elif (serial_buffer[43] == 0xA2):
                            if debug_level > 0:
                                print("AGS2 Packet")
                            value_collection['AGS2'].decode(serial_buffer)
                            sendOutput('AGS2')

                        elif (serial_buffer[43] == 0xC1):
                            if debug_level > 0:
                                print("PT1 Packet")
                            value_collection['PT1'].decode(serial_buffer)
                            sendOutput('PT1')

                        elif (serial_buffer[43] == 0xC2):
                            if debug_level > 0:
                                print("PT2 Packet")
                            value_collection['PT2'].decode(serial_buffer)
                            sendOutput('PT2')

                        elif (serial_buffer[43] == 0xC3):
                            if debug_level > 0:
                                print("PT3 Packet")
                            value_collection['PT3'].decode(serial_buffer)
                            sendOutput('PT3')

                    # Packet < 43 bytes
                    if p < (maxP-1):
                        serial_byte = mag_port.read(1)
                    if(serial_buffer[14]==0x6b):
                        value_collection['inverter'].decode(serial_buffer)
                        sendOutput('inverter')
                        if(len(serial_buffer)>35):
                            value_collection['remote_base'].decode(serial_buffer)
                            sendOutput('remote_base')
                if(printTables==1):
                    printTable()

        mag_port.close()        # close the com port and finish:

    mainLoop()

#application entry point:
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", default = "/dev/ttyUSB0", help="commuications port descriptor, e.g /dev/ttyUSB0 or COM1")
    parser.add_argument("-d", "--debug", default = 0, type=int, choices=[0, 1, 2], help="debug data")
    parser.add_argument("-m", "--mqtt", default = 0, type=int, choices=[0, 1, 2], help="Send to MQTT, 1=Publish, 2=Retain")
    parser.add_argument("-s", "--stdout", default = 1, type=int, choices=[0, 1], help="Print on StdOut")
    parser.add_argument("-t", "--table", default = 0, type=int, choices=[0, 1], help="Print Output Table (disables stdout option)")
    args = parser.parse_args()

    serial_port = args.port
    debug_level = args.debug 
    printOut = args.stdout
    printTables = args.table
    mqttOut = args.mqtt

    if(printTables==1):
        printOut=0

    if mqttOut>0:
        broker_address="localhost"
        mqttc = mqtt.Client("magnum"+serial_port[-1]) #create new instance
        mqttClock=0
        try:
            mqttc.connect(broker_address, port=1883) #connect to broker
        except:
            print("Broker Connection Failed")

    print("MagPy Magnum Energy MagnaSine Data Protocol Decoder\n")
    print("Debug level : {0}".format(debug_level))
    print("serial port : " + serial_port + "\n")

    value_collection = {}
    system_bus_volts = 0    # set as global variable:
    main()                  # call the main function:
