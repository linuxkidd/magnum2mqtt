# Magnum 2 MQTT
A tool for monitoring a Magnum inverter using Python3 and a RS-485 to serial converter, then publishing that data to an MQTT broker.

### Credits
Prior work in this arena from:
  Chris (aka user cpfl) Midnightsolar forum.
  Paul Alting van Geusau
  [Liam O'Brien](https://github.com/finderman2/MagnasineMagPy)

### Backstory
Code from earlier versions of the repostiory based heavily on work by Liam O'Brien and others noted above.

This version is a complete rewrite:
* Now uses a protocol definition file and interpreter model.
* Changed the Serial data collection to provide better synchronization to the on-the-wire protocol
* Moved the Serial collection a separate thread.
* Added better 'junk' packet rejection.

### Known issues
* For the PT-100, the documented `mode` and `regulation` ( Accessory segment `0xC1`, byte 2 ) does not follow observed data.
* ACLD Remote packet ( remote `0xD0` ) is not documented in the spec PDF file I have, thus not provided for in the spec file.

### Usage
* Copy files from `/etc` and `/usr` to system with an RS-485 serial converter.
* Reload the systemd daemon:
  ~~~
  # systemctl daemon-reload
  ~~~
* Modify options in `/etc/default/magpi` for MQTT broker and rentention based on command line options:
  ~~~
  # ./magpi.v3.py  --help
  usage: magpi.v3.py [-h] [-b BROKER] [-d {0,1,2}] [-i INTERVAL] [-p PORT] [-r]
                     [-s SPECFILE] [-t TOPIC]
  
  optional arguments:
    -h, --help            show this help message and exit
    -b BROKER, --broker BROKER
                          MQTT Broker to publish to
    -d {0,1,2}, --debug {0,1,2}
                          debug data
    -i INTERVAL, --interval INTERVAL
                          MQTT update interval ( default 1 second )
    -p PORT, --port PORT  commuications port descriptor, e.g /dev/ttyUSB0 or
                          COM1
    -r, --retain          MQTT Retain?
    -s SPECFILE, --specfile SPECFILE
                          Magnum Protocol Spec File
    -t TOPIC, --topic TOPIC
                          MQTT topic prefix
  ~~~
* Enable & Start the service, specifying the proper RS-485 serial device ( e.g. `ttyUSB0` )
  ~~~
  # systemctl enable --now magpi@ttyUSB0
  ~~~
