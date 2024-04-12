#!/usr/bin/env python

"""
Changed a lot of a Script originall created by Ralf Zimmermann (mail@ralfzimmermann.de) in 2020.
The orginal code and its documentation can be found on: https://github.com/RalfZim/venus.dbus-fronius-smartmeter
Used https://github.com/victronenergy/velib_python/blob/master/dbusdummyservice.py as basis for this service.

Links (DSTK_2023-11-27):
https://github.com/victronenergy/venus/wiki/dbus-api 
https://www.victronenergy.com/live/ccgx:modbustcp_faq
https://github.com/victronenergy/venus/wiki/howto-add-a-driver-to-Venus

/data/mqtttogrid/vedbus.py
/data/mqtttogrid/ve_utils.py
python -m ensurepip --upgrade
pip install paho-mqtt
"""

import os
import socket
import sys
import time
import logging
import logging.handlers
import platform

import paho.mqtt.client as mqtt
from vedbus import VeDbusService

if sys.version_info.major == 2:
    import gobject
    import thread   # for daemon = True  / Python 2.x
else:
    from gi.repository import GLib as gobject
    import _thread as thread   # for daemon = True  / Python 3.x

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '../ext/velib_python'))

path_UpdateIndex = '/UpdateIndex'

# MQTT Setup
broker_address = "homeassistant.local"
MQTTNAME = "MQTTtoMeter"
broker_user = "mqtttogridmeter"
broker_pw = "xxx"
Zaehlersensorpfad = "sensor/hausstrom"


# MQTT:

def on_disconnect(client, userdata, rc):  # pylint: disable=unused-argument
    logging.info('Unexpected MQTT disconnection rc=%s. Will auto-reconnect', str(rc))

    try:
        logging.info("Trying to Reconnect")
        client.connect(broker_address)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.exception("Error in Retrying to Connect with Broker", exc_info=e)


def on_connect(client, userdata, flags, rc):  # pylint: disable=unused-argument
    if rc == 0:
        logging.info("Connected to MQTT Broker!")
        ok = client.subscribe(Zaehlersensorpfad+"/#", 0)
        logging.debug("subscribed to %s ok=%s", Zaehlersensorpfad, str(ok))
    else:
        logging.warning(f"Failed to connect, return code {rc}\n")


def on_message(client, userdata, msg):  # pylint: disable=unused-argument
    try:

        if msg.topic == "sensor/hausstrom/hausstrom_sum_active_instantaneous_power":
            get_dbus_service().update(powercurr=float(msg.payload))
        elif msg.topic == "sensor/hausstrom/hausstrom_l1_active_instantaneous_power":
            get_dbus_service().update(power_l1=float(msg.payload))
        elif msg.topic == "sensor/hausstrom/hausstrom_l2_active_instantaneous_power":
            get_dbus_service().update(power_l2=float(msg.payload))
        elif msg.topic == "sensor/hausstrom/hausstrom_l3_active_instantaneous_power":
            get_dbus_service().update(power_l3=float(msg.payload))
        elif msg.topic == "sensor/hausstrom/hausstrom_positive_active_energy_total":
            get_dbus_service().update(totalin=round(float(msg.payload) / 1000, 3))
        elif msg.topic == "sensor/hausstrom/solar_energy_to_grid":
            get_dbus_service().update(totalout=round(float(msg.payload), 3))

    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.exception("MQTTtoGridMeter crashed during on_message", exc_info=e)


def log_value(value, label, unit=''):
    logging.debug(f"{label}: {value:.0f} {unit}")


class DbusDummyService:
    def __init__(self, servicename, deviceinstance, paths, productname='MQTTMeter1', connection='HA Hausstrom Dirk'):
        self._vedbusservice = VeDbusService(servicename)
        self._paths = paths

        logging.debug(f"{servicename} / DeviceInstance = {deviceinstance}")

        # Create the management objects, as specified in the ccgx dbus-api document
        self._vedbusservice.add_path('/Mgmt/ProcessName', __file__)
        self._vedbusservice.add_path('/Mgmt/ProcessVersion',
                                     'running on Python ' + platform.python_version())
        self._vedbusservice.add_path('/Mgmt/Connection', connection)

        # Create the mandatory objects
        self._vedbusservice.add_path('/DeviceInstance', deviceinstance)
        self._vedbusservice.add_path('/ProductId', 45069)  # 45069 = value used in ac_sensor_bridge.cpp of dbus-cgwacs

        # DSTK_2022-10-25: from https://github.com/fabian-lauer/dbus-shelly-3em-smartmeter/blob/main/dbus-shelly-3em-smartmeter.py
        # self._dbusservice.add_path('/ProductId', 45069) # found on https://www.sascha-curth.de/projekte/005_Color_Control_GX.html#experiment - should be an ET340 Engerie Meter
        # found on https://www.sascha-curth.de/projekte/005_Color_Control_GX.html#experiment - should be an ET340 Engerie Meter
        self._vedbusservice.add_path('/DeviceType', 345)
        self._vedbusservice.add_path('/Role', 'grid')

        self._vedbusservice.add_path('/ProductName', productname)
        self._vedbusservice.add_path('/FirmwareVersion', 0.1)
        self._vedbusservice.add_path('/HardwareVersion', 0)
        self._vedbusservice.add_path('/Connected', 0)
        self._vedbusservice.add_path('/Position', 0)  # DSTK_2022-10-25 bewirkt bei Gridmeter nichts ???
        self._vedbusservice.add_path('/UpdateIndex', 0)
        self._vedbusservice.add_path("/Serial", 1234)

        for path, settings in self._paths.items():
            self._vedbusservice.add_path(
                path, settings['initial'], gettextcallback=settings['textformat'], writeable=True, onchangecallback=self._handlechangedvalue)

        # now _update ios called from on_message:
        #   gobject.timeout_add(1000, self._update) # pause 1000ms before the next request

        self._last_update = 0
        sign_of_life_id = gobject.timeout_add(10 * 1000, self._sign_of_life)
        logging.debug(f"sign_of_life_id = {sign_of_life_id}")

    def update(self,
               powercurr=None,
               power_l1=None, power_l2=None, power_l3=None,
               totalin=None, totalout=None,
               gridloss=False):

        if gridloss:
            logging.warning("Grid lost. exit")
            self._vedbusservice['/Connected'] = 0  # does not seem to have any effect. At least no grid lost alarm
            os._exit(1)  # exit in order to disconnect and destroy the dbusservice object

        self._vedbusservice['/Connected'] = 1
        self._last_update = time.time()

        self._vedbusservice['/Ac/L1/Voltage'] = 230
        self._vedbusservice['/Ac/L2/Voltage'] = 230
        self._vedbusservice['/Ac/L3/Voltage'] = 230

        for i, power in enumerate([power_l1, power_l2, power_l3], start=1):
            if power is not None:
                self._vedbusservice[f'/Ac/L{i}/Current'] = round(power / 230, 2)
                self._vedbusservice[f'/Ac/L{i}/Power'] = power
                log_value(power, f"power_l{i}", "W")

        if totalin is not None:
            self._vedbusservice['/Ac/Energy/Forward'] = totalin  # consumption
            log_value(totalin, "totalin", "kWh")

        if totalout is not None:
            self._vedbusservice['/Ac/Energy/Reverse'] = totalout  # feed into grid
            log_value(totalout, "totalout", "kWh")

        if not powercurr is None:
            self._vedbusservice['/Ac/Power'] = powercurr  # positive: consumption, negative: feed into grid
            log_value(powercurr, "House Consumption", "W")

        self.update_dbus_index()

    def update_dbus_index(self):
        ''' increment UpdateIndex - to show that new data is available '''
        index = self._vedbusservice[path_UpdateIndex] + 1  # increment index
        if index > 255:   # maximum value of the index
            index = 0       # overflow from 255 to 0
        self._vedbusservice[path_UpdateIndex] = index

    def _sign_of_life(self):
        now = time.time()
        last_update_ago_seconds = now - self._last_update
        if last_update_ago_seconds > 10:
            logging.warning(f"last update was {last_update_ago_seconds} seconds ago.")
            self.update(gridloss=True)
        else:
            logging.debug(f"ok: last update was {last_update_ago_seconds} seconds ago.")
        return True  # must return True if it wants to be rescheduled

    def _handlechangedvalue(self, path, value):
        logging.debug(f"someone else updated {path} to {value}")
        return True  # accept the change


def init_mqtt():
    client = mqtt.Client(MQTTNAME)  # create new instance
    client.username_pw_set(broker_user, broker_pw)
    client.on_disconnect = on_disconnect
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker_address)  # connect to broker

    client.loop_start()


def init_logging():
    logging.basicConfig(
        format="%(asctime)s,%(msecs)d %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.DEBUG,
        handlers=[
            logging.StreamHandler(),
        ],
    )
    syslog_handler = logging.handlers.SysLogHandler(address="/dev/log")
    syslog_handler.setLevel(level=logging.DEBUG)
    syslog_handler.setFormatter(logging.Formatter(
        f"{socket.gethostname()} mqtttogrid %(asctime)s,%(msecs)d %(levelname)s %(message)s"))
    logging.getLogger().addHandler(syslog_handler)

    file_handler = logging.FileHandler(f"{(os.path.dirname(os.path.realpath(__file__)))}/current.log")
    file_handler.setLevel(level=logging.INFO)
    file_handler.setFormatter(logging.Formatter(f"%(asctime)s,%(msecs)d %(levelname)s %(message)s"))
    logging.getLogger().addHandler(file_handler)


def get_dbus_service():
    # formatting
    def _kwh(p, v): return (str(round(v, 2)) + 'kWh')
    def _wh(p, v): return (str(round(v, 2)) + 'Wh')
    def _a(p, v): return (str(round(v, 2)) + 'A')
    def _w(p, v): return (str(int(round(v, 0))) + 'W')
    def _v(p, v): return (str(round(v, 1)) + 'V')
    def _hz(p, v): return (str(round(v, 2)) + 'Hz')

    if get_dbus_service.dbusservice is None:
        get_dbus_service.dbusservice = DbusDummyService(
            # servicename='com.victronenergy.grid',
            servicename='com.victronenergy.grid.cgwacs_edl21_ha',
            deviceinstance=31,  # = VRM instance ID
            paths={
                '/Ac/Power': {'initial': None, 'textformat': _w},
                '/Ac/L1/Voltage': {'initial': None, 'textformat': _v},
                '/Ac/L2/Voltage': {'initial': None, 'textformat': _v},
                '/Ac/L3/Voltage': {'initial': None, 'textformat': _v},
                '/Ac/L1/Current': {'initial': None, 'textformat': _a},
                '/Ac/L2/Current': {'initial': None, 'textformat': _a},
                '/Ac/L3/Current': {'initial': None, 'textformat': _a},
                '/Ac/L1/Power': {'initial': None, 'textformat': _w},
                '/Ac/L2/Power': {'initial': None, 'textformat': _w},
                '/Ac/L3/Power': {'initial': None, 'textformat': _w},
                '/Ac/Energy/Forward': {'initial': None, 'textformat': _kwh},  # energy bought from the grid
                '/Ac/Energy/Reverse': {'initial': None, 'textformat': _kwh},  # energy sold to the grid
            })
        logging.info('Connected to dbus')

    return get_dbus_service.dbusservice


get_dbus_service.dbusservice = None


def main():
    init_logging()
    init_mqtt()

    thread.daemon = True  # allow the program to quit

    from dbus.mainloop.glib import DBusGMainLoop
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)

    logging.debug('Switching over to gobject.MainLoop() (= event based)')
    mainloop = gobject.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()
