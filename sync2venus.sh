rsync \
  -rltv \
  --exclude '.git' \
  --exclude 'pics' \
  --exclude '.vscode' \
  --exclude '.pylintrc' \
  --exclude '.DS_Store' \
  --exclude 'dbus-fronius-smartmeter.py' \
  --exclude '*.log' \
  ../venus.dbus-MqttToGridMeter/ root@venus.steinkopf.net:/data/mqtttogrid/
