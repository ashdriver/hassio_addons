#!/usr/bin/with-contenv bashio
export TERM=xterm
export DEVICE=$(bashio::config 'Inverter_device')
export LOG_LEVEL=$(bashio::config 'Log_level')

# MQTT connection: use add-on options if a username is set, otherwise use the
# credentials provided by the Mosquitto add-on (mqtt service).
if bashio::config.has_value 'MQTT_USERNAME'; then
    MQTT_HOST=$(bashio::config 'MQTT_HOST' 'core-mosquitto')
    MQTT_PORT=$(bashio::config 'MQTT_PORT' '1883')
    MQTT_USERNAME=$(bashio::config 'MQTT_USERNAME')
    MQTT_PASSWORD=$(bashio::config 'MQTT_PASSWORD')
    bashio::log.info "Using MQTT credentials from add-on options (user ${MQTT_USERNAME})"
else
    MQTT_HOST=$(bashio::services mqtt 'host')
    MQTT_PORT=$(bashio::services mqtt 'port')
    MQTT_USERNAME=$(bashio::services mqtt 'username')
    MQTT_PASSWORD=$(bashio::services mqtt 'password')
    bashio::log.info "Using MQTT credentials from the Mosquitto add-on"
fi
jq --arg h "$MQTT_HOST" --arg p "$MQTT_PORT" --arg u "$MQTT_USERNAME" --arg pw "$MQTT_PASSWORD" \
    '.server=$h | .port=$p | .username=$u | .password=$pw' \
    /etc/inverter/mqtt.json > /tmp/mqtt.json && mv /tmp/mqtt.json /etc/inverter/mqtt.json

# stty -F /dev/ttyUSB0 2400 raw

# Init the mqtt server for the first time, then every 5 minutes
# This will re-create the auto-created topics in the MQTT server if HA is restarted...

watch -n 300 '/opt/inverter-mqtt/mqtt-init.sh > /dev/null 2>&1 ' &

# Run the MQTT Subscriber process in the background (so that way we can change the configuration on the inverter from home assistant)
/opt/inverter-mqtt/mqtt-subscriber.sh  &

# execute exactly every 30 seconds...
watch -n 30 '/opt/inverter-mqtt/mqtt-push.sh > /dev/null 2>&1; ls -lsa /dev/hidraw? '
