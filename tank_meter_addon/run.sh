#!/usr/bin/with-contenv bashio

export MQTT_HOST=$(bashio::config 'MQTT_HOST')
export MQTT_PORT=$(bashio::config 'MQTT_PORT')
export MQTT_USERNAME=$(bashio::config 'MQTT_USERNAME')
export MQTT_PASSWORD=$(bashio::config 'MQTT_PASSWORD')
export LOG_LEVEL=$(bashio::config 'Log_level')

python /app/getAngle.py $MQTT_HOST $MQTT_PORT $MQTT_USERNAME $MQTT_PASSWORD $LOG_LEVEL
