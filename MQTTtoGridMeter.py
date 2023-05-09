#!/usr/bin/env python

"""
Changed a lot of a Script originall created by Ralf Zimmermann (mail@ralfzimmermann.de) in 2020.
The orginal code and its documentation can be found on: https://github.com/RalfZim/venus.dbus-fronius-smartmeter
Used https://github.com/victronenergy/velib_python/blob/master/dbusdummyservice.py as basis for this service.
"""

"""
/data/mqtttogrid/vedbus.py
/data/mqtttogrid/ve_utils.py
python -m ensurepip --upgrade
pip install paho-mqtt
"""
try:
  import gobject  # Python 2.x
except:
  from gi.repository import GLib as gobject # Python 3.x
import platform
import logging
import time
import sys
import json
import os
import paho.mqtt.client as mqtt
try:
  import thread   # for daemon = True  / Python 2.x
except:
  import _thread as thread   # for daemon = True  / Python 3.x

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '../ext/velib_python'))
from vedbus import VeDbusService

path_UpdateIndex = '/UpdateIndex'

# MQTT Setup
broker_address = "homeassistant.local"
MQTTNAME = "MQTTtoMeter"
broker_user = "mqtttogridmeter"
broker_pw = "xxx"
Zaehlersensorpfad = "sensor/hausstrom"

# Variablen setzen
verbunden = 0
powercurr = None
totalin = None
totalout = None
power_l1 = None
power_l2 = None
power_l3 = None
l_avg = None
dbusservice = None


# MQTT Abfragen:

def on_disconnect(client, userdata, rc):
    global verbunden
    print("MQTT client Got Disconnected")
    if rc != 0:
        print('Unexpected MQTT disconnection. Will auto-reconnect')

    else:
        print('rc value:' + str(rc))

    try:
        print("Trying to Reconnect")
        client.connect(broker_address)
        verbunden = 1
    except Exception as e:
        logging.exception("Fehler beim reconnecten mit Broker")
        print("Error in Retrying to Connect with Broker")
        verbunden = 0
        print(e)

def on_connect(client, userdata, flags, rc):
        global verbunden
        if rc == 0:
            print("Connected to MQTT Broker!")
            verbunden = 1
            ok = client.subscribe(Zaehlersensorpfad+"/#", 0)
            print("subscribed to "+Zaehlersensorpfad+" ok="+str(ok))
        else:
            print("Failed to connect, return code %d\n" % rc)


def on_message(client, userdata, msg):

    try:

        global powercurr, totalin, totalout, power_l1, power_l2, power_l3, l_avg, dbusservice
        if msg.topic == "sensor/hausstrom/hausstrom_sum_active_instantaneous_power":
            powercurr = float(msg.payload)
        elif msg.topic == "sensor/hausstrom/hausstrom_l1_active_instantaneous_power":
            power_l1 = float(msg.payload)
        elif msg.topic == "sensor/hausstrom/hausstrom_l2_active_instantaneous_power":
            power_l2 = float(msg.payload)
        elif msg.topic == "sensor/hausstrom/hausstrom_l3_active_instantaneous_power":
            power_l3 = float(msg.payload)
        elif msg.topic == "sensor/hausstrom/hausstrom_positive_active_energy_total":
            totalin = round(float(msg.payload) / 1000, 3)
        elif msg.topic == "sensor/hausstrom/solar_energy_to_grid":
            totalout = round(float(msg.payload), 3)

        #if not power_l1 is None and not power_l2 is None and not power_l3 is None:
        #    l_avg = (power_l1 + power_l2 + power_l3) / 3

        dbusservice._update()

    except Exception as e:
        logging.exception("Programm MQTTtoMeter ist abgestuerzt. (during on_message function)")
        print(e)
        print("Im MQTTtoMeter Programm ist etwas beim auslesen der Nachrichten schief gegangen")




class DbusDummyService:
  def __init__(self, servicename, deviceinstance, paths, productname='MQTTMeter1', connection='HA Hausstrom Dirk'):
    self._dbusservice = VeDbusService(servicename)
    self._paths = paths

    logging.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))

    # Create the management objects, as specified in the ccgx dbus-api document
    self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
    self._dbusservice.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
    self._dbusservice.add_path('/Mgmt/Connection', connection)

    # Create the mandatory objects
    self._dbusservice.add_path('/DeviceInstance', deviceinstance)
    self._dbusservice.add_path('/ProductId', 45069) # 45069 = value used in ac_sensor_bridge.cpp of dbus-cgwacs

    # DSTK_2022-10-25: from https://github.com/fabian-lauer/dbus-shelly-3em-smartmeter/blob/main/dbus-shelly-3em-smartmeter.py
    #self._dbusservice.add_path('/ProductId', 45069) # found on https://www.sascha-curth.de/projekte/005_Color_Control_GX.html#experiment - should be an ET340 Engerie Meter
    self._dbusservice.add_path('/DeviceType', 345) # found on https://www.sascha-curth.de/projekte/005_Color_Control_GX.html#experiment - should be an ET340 Engerie Meter
    self._dbusservice.add_path('/Role', 'grid')


    self._dbusservice.add_path('/ProductName', productname)
    self._dbusservice.add_path('/FirmwareVersion', 0.1)
    self._dbusservice.add_path('/HardwareVersion', 0)
    self._dbusservice.add_path('/Connected', 1)
    self._dbusservice.add_path('/Position', 0) # DSTK_2022-10-25 bewirkt nichts ???
    self._dbusservice.add_path('/UpdateIndex', 0)

    for path, settings in self._paths.items():
      self._dbusservice.add_path(
        path, settings['initial'], gettextcallback=settings['textformat'], writeable=True, onchangecallback=self._handlechangedvalue)

    # now _update ios called from on_message: 
    #   gobject.timeout_add(1000, self._update) # pause 1000ms before the next request

  
  def _update(self):

    if not powercurr is None: self._dbusservice['/Ac/Power'] =  powercurr # positive: consumption, negative: feed into grid
    self._dbusservice['/Ac/L1/Voltage'] = 230
    self._dbusservice['/Ac/L2/Voltage'] = 230
    self._dbusservice['/Ac/L3/Voltage'] = 230
    if not l_avg is None:
        self._dbusservice['/Ac/L1/Current'] = round(l_avg / 230 ,2)
        self._dbusservice['/Ac/L2/Current'] = round(l_avg / 230 ,2)
        self._dbusservice['/Ac/L3/Current'] = round(l_avg / 230 ,2)
        self._dbusservice['/Ac/L1/Power'] = l_avg
        self._dbusservice['/Ac/L2/Power'] = l_avg
        self._dbusservice['/Ac/L3/Power'] = l_avg
    else:
        if not power_l1 is None: self._dbusservice['/Ac/L1/Current'] = round(power_l1 / 230, 2)
        if not power_l2 is None: self._dbusservice['/Ac/L2/Current'] = round(power_l2 / 230, 2)
        if not power_l3 is None: self._dbusservice['/Ac/L3/Current'] = round(power_l3 / 230, 2)
        if not power_l1 is None: self._dbusservice['/Ac/L1/Power'] = power_l1
        if not power_l2 is None: self._dbusservice['/Ac/L2/Power'] = power_l2
        if not power_l3 is None: self._dbusservice['/Ac/L3/Power'] = power_l3

    if not totalin is None: self._dbusservice['/Ac/Energy/Forward'] = totalin
    if not totalout is None: self._dbusservice['/Ac/Energy/Reverse'] = totalout

    if not powercurr is None: logging.debug("House Consumption: {:.0f} W".format(powercurr))
    if not power_l3 is None: logging.debug("power_l3: {:.0f} W".format(power_l3))
    if not totalin is None: logging.debug("totalin: {:.0f} kWh".format(totalin))
    if not totalout is None: logging.debug(f"totalout: {totalout} kWh")

    # increment UpdateIndex - to show that new data is available
    index = self._dbusservice[path_UpdateIndex] + 1  # increment index
    if index > 255:   # maximum value of the index
      index = 0       # overflow from 255 to 0
    self._dbusservice[path_UpdateIndex] = index

    self._lastUpdate = time.time()

    return True

  def _handlechangedvalue(self, path, value):
    logging.debug("someone else updated %s to %s" % (path, value))
    return True # accept the change

def main():
  #logging.basicConfig(level=logging.INFO) # use .INFO for less, .DEBUG for more logging
  logging.basicConfig(
      format="%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S",
      level=logging.INFO,
      # level=logging.DEBUG,
      handlers=[
          logging.FileHandler(f"{(os.path.dirname(os.path.realpath(__file__)))}/current.log"),
          logging.StreamHandler(),
      ],
  )
  thread.daemon = True # allow the program to quit

  from dbus.mainloop.glib import DBusGMainLoop
  # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
  DBusGMainLoop(set_as_default=True)
  
  # formatting
  def _kwh(p, v): return (str(round(v, 2)) + 'kWh')
  def _wh(p, v): return (str(round(v, 2)) + 'Wh')
  def _a(p, v): return (str(round(v, 2)) + 'A')
  def _w(p, v): return (str(int(round(v, 0))) + 'W')
  def _v(p, v): return (str(round(v, 1)) + 'V')
  def _hz(p, v): return (str(round(v, 2)) + 'Hz')

  global dbusservice
  dbusservice = DbusDummyService(
    #servicename='com.victronenergy.grid',
    servicename='com.victronenergy.grid.cgwacs_edl21_ha',
    deviceinstance=0,
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
      '/Ac/Energy/Forward': {'initial': None, 'textformat': _kwh}, # energy bought from the grid
      '/Ac/Energy/Reverse': {'initial': None, 'textformat': _kwh}, # energy sold to the grid
    })

  logging.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
  mainloop = gobject.MainLoop()
  mainloop.run()

# Konfiguration MQTT
client = mqtt.Client(MQTTNAME) # create new instance
client.username_pw_set(broker_user, broker_pw)
client.on_disconnect = on_disconnect
client.on_connect = on_connect
client.on_message = on_message
client.connect(broker_address)  # connect to broker

client.loop_start()

if __name__ == "__main__":
  main()