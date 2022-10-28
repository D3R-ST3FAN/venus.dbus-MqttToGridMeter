# dbus-MQTT to Grid Meter Service

### Disclaimer

This Script/Project was forked from Marv2190/venus.dbus-MqttToGridMeter 
which in turn was forked from RalfZim/venus.dbus-fronius-smartmeter. 
I updated this to work with my home assistant installation MQTT source.

You have to run Paho Client on your GXDevice to make this script work

python -m ensurepip --upgrade
pip install paho-mqtt


### Purpose

The Python script cyclically reads data from a home assistant MQTT Broker and publishes information 
on the dbus, using the service name com.victronenergy.grid.cgwacs_edl21_ha. 
This makes the Venus OS work as if you had a physical Victron Grid Meter installed.

### Configuration

In the Python file, you should put the IP or name of your Broker. And probably update the MQTT topics.

### Installation

1. Copy the files to the /data folder on your venus:

    Copy the files to the /data folder on your venus:

        sync -rltv --exclude '.git' --exclude 'pics' --exclude '.DS_Store' --exclude 'dbus-fronius-smartmeter.py'  ../venus.dbus-MqttToGridMeter/ root@venus:/data/mqtttogrid/

2. Set permissions for files:

    chmod 755 /data/mqtttogrid/service/run

    chmod 744 /data/mqtttogrid/kill_me.sh


3. Get two files from the [velib_python](https://github.com/victronenergy/velib_python) and install them on your venus:

    (For convenience I already added the current version to this repo. So this step could be skipped - or updated them from the origin.)

        /data/mqtttogrid/vedbus.py
        /data/mqtttogrid/ve_utils.py


4. Install the service (= add a symlink to the file /data/rc.local) by:

   `bash -x /data/mqtttogrid/install.sh`

   The daemon-tools should automatically start this service within seconds.


### Debugging

You can check the status of the service with svstat:

`svstat /service/mqtttogrid`

It will show something like this:

`/service/mqtttogrid: up (pid 10078) 325 seconds`

If the number of seconds is always 0 or 1 or any other small number, it means that the service crashes and gets restarted all the time.

When you think that the script crashes, start it directly from the command line:

`python /data/mqtttogrid/MQTTtoGridMeter.py`

and see if it throws any error messages.

If the script stops with the message

`dbus.exceptions.NameExistsException: Bus name already exists: com.victronenergy.grid"`

it means that the service is still running or another service is using that bus name.

#### Restart the script

If you want to restart the script, for example after changing it, just run the following command:

`/data/mqtttogrid/kill_me.sh`

The daemon-tools will restart the scriptwithin a few seconds.


### Star this Project if you like it. If you need help start an issue :)

...or maybe one of the forked projects (see above).