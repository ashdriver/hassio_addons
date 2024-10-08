#!/usr/bin/with-contenv bashio

export CENTRE_X=$(bashio::config 'centre_x')
export CENTRE_Y=$(bashio::config 'centre_y')
export TOLERANCE=$(bashio::config 'tolerance')
export MQTT_HOST=$(bashio::config 'MQTT_HOST')
export MQTT_PORT=$(bashio::config 'MQTT_PORT')
export MQTT_USERNAME=$(bashio::config 'MQTT_USERNAME')
export MQTT_PASSWORD=$(bashio::config 'MQTT_PASSWORD')
export LOG_LEVEL=$(bashio::config 'Log_level')

python /app/getAngle.py
