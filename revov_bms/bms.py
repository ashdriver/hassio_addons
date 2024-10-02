

import paho.mqtt.client as mqtt
import socket
import time
import yaml
import os
import json
import serial
import io
import json
import atexit
import sys
import constants
import numpy as np

print("Starting up...")

config = {}
script_version = ""

if os.path.exists('/data/options.json'):
    print("Loading options.json")
    with open(r'/data/options.json') as file:
        config = json.load(file)
        print("Config: " + json.dumps(config))

elif os.path.exists('revov_bms\\config.yaml'):
    print("Loading config.yaml")
    with open(r'revov_bms\\config.yaml') as file:
        config = yaml.load(file, Loader=yaml.FullLoader)['options']

else:
    sys.exit("No config file found")


scan_interval = config['scan_interval']
connection_type = config['connection_type']
bms_serial = config['bms_serial']
ha_discovery_enabled = config['mqtt_ha_discovery']
code_running = True
bms_connected = False
mqtt_connected = False
print_initial = True
debug_output = config['debug_output']
disc_payload = {}
repub_discovery = 0

bms_version = ''
bms_sn = ''
pack_sn = ''
packs = 1
cells = 13
temps = 6


print("Connection Type: " + connection_type)

def on_connect(client, userdata, flags, rc):
    print("MQTT connected with result code "+str(rc))
    client.will_set(config['mqtt_base_topic'] + "/availability","offline", qos=0, retain=False)
    global mqtt_connected
    mqtt_connected = True

def on_disconnect(client, userdata, rc):
    print("MQTT disconnected with result code "+str(rc))
    global mqtt_connected
    mqtt_connected = False

client = mqtt.Client("bms")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
#client.on_message = on_message

client.username_pw_set(username=config['mqtt_user'], password=config['mqtt_password'])
client.connect(config['mqtt_host'], config['mqtt_port'], 60)
client.loop_start()
time.sleep(2)

def exit_handler():
    print("Script exiting")
    client.publish(config['mqtt_base_topic'] + "/availability","offline")
    return

atexit.register(exit_handler)

def bms_connect(address, port):

    if connection_type == "Serial":

        try:
            print("trying to connect %s" % bms_serial)
            s = serial.Serial(bms_serial,timeout = 1)
            print("BMS serial connected")
            return s, True
        except IOError as msg:
            print("BMS serial error connecting: %s" % msg)
            return False, False

    else:

        try:
            print("trying to connect " + address + ":" + str(port))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((address, port))
            print("BMS socket connected")
            return s, True
        except OSError as msg:
            print("BMS socket error connecting: %s" % msg)
            return False, False

def bms_sendData(comms,request=''):

    if connection_type == "Serial":

        try:
            if len(request) > 0:
                comms.write(request)
                time.sleep(0.25)
                return True
        except IOError as e:
            print("BMS serial error: %s" % e)
            # global bms_connected
            return False

    else:

        try:
            if len(request) > 0:
                comms.send(request)
                time.sleep(0.25)
                return True
        except Exception as e:
            print("BMS socket error: %s" % e)
            # global bms_connected
            return False

def bms_get_data(comms):
    try:
        if connection_type == "Serial":
            inc_data = comms.readline()
        else:
            temp = bytes()

            while len(temp) == 0 or temp[-1] != 13:
                temp = temp + comms.recv(4096)

            temp2 = temp.split(b'\r')
            # Decide which one to take:
            for element in range(0,len(temp2)):
                SOI = hex(ord(temp2[element][0:1]))
                if SOI == '0x7e':
                    inc_data = temp2[element] + b'\r'
                    break

            if (len(temp2) > 2) & (debug_output > 0):
                print("Multiple EOIs detected")
                print("...for incoming data: " + str(temp) + " |Hex: " + str(temp.hex(' ')))

        return inc_data
    except Exception as e:
        print("BMS socket receive error: %s" % e)
        # global bms_connected
        return False

def ha_discovery():

    global ha_discovery_enabled
    global packs

    if ha_discovery_enabled:

        print("Publishing HA Discovery topic...")

        disc_payload['availability_topic'] = config['mqtt_base_topic'] + "/availability"

        device = {}
        device['manufacturer'] = "BMS TIAN"
        device['model'] = "AM-x"
        device['identifiers'] = "bms_" + bms_sn
        device['name'] = "Generic Lithium"
        device['sw_version'] = bms_version
        disc_payload['device'] = device

        for p in range (1,packs+1):

            for i in range(0,cells):
                disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Cell " + str(i+1).zfill(config['zero_pad_number_cells']) + " Voltage"
                disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_v_cell_" + str(i+1).zfill(config['zero_pad_number_cells'])
                disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/v_cells/cell_" + str(i+1).zfill(config['zero_pad_number_cells'])
                disc_payload['unit_of_measurement'] = "mV"
                client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            for i in range(0,temps):
                disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Temperature " + str(i+1)
                disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_temp_" + str(i+1)
                disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/temps/temp_" + str(i+1)
                disc_payload['unit_of_measurement'] = "°C"
                client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "MOS_Temp"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_t_mos"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/t_mos"
            disc_payload['unit_of_measurement'] = "°C"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'] + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Environmental_Temp"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_t_env"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/t_env"
            disc_payload['unit_of_measurement'] = "°C"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'] + "/config",json.dumps(disc_payload),qos=0, retain=True)
 
            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Current"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_i_pack"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/i_pack"
            disc_payload['unit_of_measurement'] = "A"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Voltage"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_v_pack"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/v_pack"
            disc_payload['unit_of_measurement'] = "V"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Remaining Capacity"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_i_remain_cap"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/i_remain_cap"
            disc_payload['unit_of_measurement'] = "Ah"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " State of Health"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_soh"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/soh"
            disc_payload['unit_of_measurement'] = "%"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Cycles"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_cycles"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/cycles"
            disc_payload['unit_of_measurement'] = ""
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Full Capacity"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_i_full_cap"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/i_full_cap"
            disc_payload['unit_of_measurement'] = "Ah"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Design Capacity"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_i_design_cap"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/i_design_cap"
            disc_payload['unit_of_measurement'] = "Ah"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " State of Charge"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_soc"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/soc"
            disc_payload['unit_of_measurement'] = "%"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " State of Health"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_soh"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/soh"
            disc_payload['unit_of_measurement'] = "%"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload.pop('unit_of_measurement')

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Protections"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_protections"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/protections"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Alarms"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_alarms"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/alarms"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " States"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_states"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/states"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Balancing"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_balancing"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/balancing"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            # Binary Sensors
            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + "Charging"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_charging"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/charging"
            disc_payload['payload_on'] = "1"
            disc_payload['payload_off'] = "0"
            client.publish(config['mqtt_ha_discovery_topic']+"/binary_sensor/BMS-" + bms_sn + "/" + disc_payload['name'] + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + "Discharging"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_discharging"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/discharging"
            disc_payload['payload_on'] = "1"
            disc_payload['payload_off'] = "0"
            client.publish(config['mqtt_ha_discovery_topic']+"/binary_sensor/BMS-" + bms_sn + "/" + disc_payload['name'] + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Protection Short Circuit"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_prot_short_circuit"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/prot_short_circuit"
            disc_payload['payload_on'] = "1"
            disc_payload['payload_off'] = "0"
            client.publish(config['mqtt_ha_discovery_topic']+"/binary_sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Protection Discharge Current"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_prot_discharge_current"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/prot_discharge_current"
            disc_payload['payload_on'] = "1"
            disc_payload['payload_off'] = "0"
            client.publish(config['mqtt_ha_discovery_topic']+"/binary_sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Protection Charge Current"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_prot_charge_current"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/prot_charge_current"
            disc_payload['payload_on'] = "1"
            disc_payload['payload_off'] = "0"
            client.publish(config['mqtt_ha_discovery_topic']+"/binary_sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Current Limit"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_current_limit"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/current_limit"
            disc_payload['payload_on'] = "1"
            disc_payload['payload_off'] = "0"
            client.publish(config['mqtt_ha_discovery_topic']+"/binary_sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Charge FET"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_charge_fet"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/charge_fet"
            disc_payload['payload_on'] = "1"
            disc_payload['payload_off'] = "0"
            client.publish(config['mqtt_ha_discovery_topic']+"/binary_sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Discharge FET"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_discharge_fet"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/discharge_fet"
            disc_payload['payload_on'] = "1"
            disc_payload['payload_off'] = "0"
            client.publish(config['mqtt_ha_discovery_topic']+"/binary_sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Reverse"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_reverse"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/reverse"
            disc_payload['payload_on'] = "1"
            disc_payload['payload_off'] = "0"
            client.publish(config['mqtt_ha_discovery_topic']+"/binary_sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            disc_payload['name'] = "Pack " + str(p).zfill(config['zero_pad_number_packs']) + " Cell Max Volt Diff"
            disc_payload['unique_id'] = "bms_" + bms_sn + "_pack_" + str(p).zfill(config['zero_pad_number_packs']) + "_cells_max_diff_calc"
            disc_payload['state_topic'] = config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/cells_max_diff_calc"
            disc_payload['unit_of_measurement'] = "mV"
            client.publish(config['mqtt_ha_discovery_topic']+"/sensor/BMS-" + bms_sn + "/" + disc_payload['name'].replace(' ', '_') + "/config",json.dumps(disc_payload),qos=0, retain=True)

            # Pack data
            disc_payload.pop('payload_on')
            disc_payload.pop('payload_off')

    else:
        print("HA Discovery Disabled")

def chksum_calc(data):

    global debug_output
    chksum = 0

    try:

        for element in range(1, len(data)): #-5):
            chksum += (data[element])

        chksum = chksum % 65536
        chksum = '{0:016b}'.format(chksum)

        flip_bits = ''
        for i in chksum:
            if i == '0':
                flip_bits += '1'
            else:
                flip_bits += '0'

        chksum = flip_bits
        chksum = int(chksum,2)+1

        chksum = format(chksum, 'X')

    except Exception as e:
        if debug_output > 0:
            print("Error calculating CHKSUM using data: " + data)
            print("Error details: ", str(e))
        return(False)

    return(chksum)

def cid2_rtn(rtn):

    # RTN Reponse codes, looking for errors
    if rtn == b'00':
        return False, False
    elif rtn == b'01':
        return True, "RTN Error 01: Undefined RTN error"
    elif rtn == b'02':
        return True, "RTN Error 02: CHKSUM error"
    elif rtn == b'03':
        return True, "RTN Error 03: LCHKSUM error"
    elif rtn == b'04':
        return True, "RTN Error 04: CID2 undefined"
    elif rtn == b'05':
        return True, "RTN Error 05: Undefined error"
    elif rtn == b'06':
        return True, "RTN Error 06: Undefined error"
    elif rtn == b'09':
        return True, "RTN Error 09: Operation or write error"
    else:
        return False, False

def bms_parse_data(inc_data):

    global debug_output

    #inc_data = b'~25014600D0F40002100DD50DBC0DD70DD70DD40DD70DD20DD50DD30DD60DC10DD40DD50DD70DD30DD5060B760B710B700B7A0B7D0B9D0000DD2326A90226AC011126AC64100DD30DBD0DD40DC60DD50DD40DD50DD50DD60DD60DD40DD20DD30\r'

    try:

        SOI = hex(ord(inc_data[0:1]))
        if SOI != '0x7e':
            return(False,"Incorrect starting byte for incoming data")

        if debug_output > 1:
            print("SOI: ", SOI)
            print("VER: ", inc_data[1:3])
            print("ADR: ", inc_data[3:5])
            print("CID1 (Type): ", inc_data[5:7])

        RTN = inc_data[7:9]
        error, info = cid2_rtn(RTN)
        if error:
            print(info)
            raise Exception(info)
        LCHKSUM = inc_data[9]
        if debug_output > 1:
            print("RTN: ", RTN)
            print("LENGTH: ", inc_data[9:13])
            print(" - LCHKSUM: ", LCHKSUM)
            print(" - LENID: ", inc_data[10:13])

        LENID = int(inc_data[10:13],16) #amount of bytes, i.e. 2x hex

        calc_LCHKSUM = lchksum_calc(inc_data[10:13])
        if calc_LCHKSUM == False:
            return(False,"Error calculating LCHKSUM for incoming data")

        if LCHKSUM != ord(calc_LCHKSUM):
            if debug_output > 0:
                print("LCHKSUM received: " + str(LCHKSUM) + " does not match calculated: " + str(ord(calc_LCHKSUM)))
            return(False,"LCHKSUM received: " + str(LCHKSUM) + " does not match calculated: " + str(ord(calc_LCHKSUM)))

        if debug_output > 1:
            print(" - LENID (int): ", LENID)

        INFO = inc_data[13:13+LENID]

        if debug_output > 1:
            print("INFO: ", INFO)

        CHKSUM = inc_data[13+LENID:13+LENID+4]

        if debug_output > 1:
            print("CHKSUM: ", CHKSUM)
            #print("EOI: ", hex(inc_data[13+LENID+4]))

        calc_CHKSUM = chksum_calc(inc_data[:len(inc_data)-5])


        if debug_output > 1:
            print("Calc CHKSUM: ", calc_CHKSUM)
    except Exception as e:
        if debug_output > 0:
            print("Error1 calculating CHKSUM using data: ", inc_data)
        return(False,"Error1 calculating CHKSUM: " + str(e))

    if calc_CHKSUM == False:
        if debug_output > 0:
            print("Error2 calculating CHKSUM using data: ", inc_data)
        return(False,"Error2 calculating CHKSUM")

    if CHKSUM.decode("ASCII") == calc_CHKSUM:
        return(True,INFO)
    else:
        if debug_output > 0:
            print("Received and calculated CHKSUM does not match: Received: " + CHKSUM.decode("ASCII") + ", Calculated: " + calc_CHKSUM)
            print("...for incoming data: " + str(inc_data) + " |Hex: " + str(inc_data.hex(' ')))
            print("Length of incoming data as measured: " + str(len(inc_data)))
            print("SOI: ", SOI)
            print("VER: ", inc_data[1:3])
            print("ADR: ", inc_data[3:5])
            print("CID1 (Type): ", inc_data[5:7])
            print("RTN (decode!): ", RTN)
            print("LENGTH: ", inc_data[9:13])
            print(" - LCHKSUM: ", inc_data[9])
            print(" - LENID: ", inc_data[10:13])
            print(" - LENID (int): ", int(inc_data[10:13],16))
            print("INFO: ", INFO)
            print("CHKSUM: ", CHKSUM)
            #print("EOI: ", hex(inc_data[13+LENID+4]))
        return(False,"Checksum error")

def lchksum_calc(lenid):

    chksum = 0

    try:

        # for element in range(1, len(lenid)): #-5):
        #     chksum += (lenid[element])

        for element in range(0, len(lenid)):
            chksum += int(chr(lenid[element]),16)

        chksum = chksum % 16
        chksum = '{0:04b}'.format(chksum)

        flip_bits = ''
        for i in chksum:
            if i == '0':
                flip_bits += '1'
            else:
                flip_bits += '0'

        chksum = flip_bits
        chksum = int(chksum,2)

        chksum += 1

        if chksum > 15:
            chksum = 0

        chksum = format(chksum, 'X')

    except:

        print("Error calculating LCHKSUM using LENID: ", lenid)
        return(False)

    return(chksum)

def bms_request(bms, ver=b"\x32\x32",adr=b"\x30\x31",cid1=b"\x34\x41",cid2=b"\x43\x31",info=b"",LENID=False):

    global bms_connected
    global debug_output

    request = b'\x7e'
    request += ver
    request += adr
    request += cid1
    request += cid2

    if not(LENID):
        LENID = len(info)
        #print("Length: ", LENID)
        LENID = bytes(format(LENID, '03X'), "ASCII")

    #print("LENID: ", LENID)

    if LENID == b'000':
        LCHKSUM = '0'
    else:
        LCHKSUM = lchksum_calc(LENID)
        if LCHKSUM == False:
            return(False,"Error calculating LCHKSUM)")
    #print("LCHKSUM: ", LCHKSUM)
    request += bytes(LCHKSUM, "ASCII")
    request += LENID
    request += info
    CHKSUM = bytes(chksum_calc(request), "ASCII")
    if CHKSUM == False:
        return(False,"Error calculating CHKSUM)")
    request += CHKSUM
    request += b'\x0d'

    if debug_output > 2:
        print("-> Outgoing Data: ", request)

    if not bms_sendData(bms,request):
        bms_connected = False
        print("Error, connection to BMS lost")
        return(False,"Error, connection to BMS lost")

    inc_data = bms_get_data(bms)

    if inc_data == False:
        print("Error retrieving data from BMS")
        return(False,"Error retrieving data from BMS")

    if debug_output > 2:
        print("<- Incoming data: ", inc_data)

    success, INFO = bms_parse_data(inc_data)

    return(success, INFO)

def bms_getSerial(comms):
    global bms_sn
    global pack_sn
    bms_sn = "TIANBMS01"
    pack_sn = "REVOVSX2"
    client.publish(config['mqtt_base_topic'] + "/bms_sn",bms_sn)
    client.publish(config['mqtt_base_topic'] + "/pack_sn",pack_sn)
    print("BMS Serial Number: " + bms_sn)
    print("Pack Serial Number: " + pack_sn)

    return(True,bms_sn,pack_sn)

def bms_getData(bms,batNumber):

    global print_initial
    global cells
    global temps
    global packs
    byte_index = 0
    i_pack = []
    v_pack = []
    i_remain_cap = []
    i_design_cap = []
    cycles = []
    i_full_cap = []
    soc = []
    soh = []

    battery = bytes(format(batNumber, '02X'), 'ASCII')

    success, inc_data = bms_request(bms,cid2=constants.cid2PackAnalogData,info=battery)

    if success == False:
      return(False,inc_data)


    #bms_request -> bms_get_data(inc_data/INFO = bms_parse_data)

    #prefix: ~250146006118
    #To test set: inc_data = INFO
    #inc_data = b'000A100CF40CF40CF40CF50CF30CF40CF40CF30CF80CF30CF30CF30CF30CF50CF40CF4060B2E0B300B2D0B300B3B0B47FEFCCF406B58096D2700146D60626D606D606D606D6064D1180000100000000000000000000000000000000000000000000000000000000000000000060AAA0AAA0AAA0AAA0AAA0AAA000000000000090000000000006200000000000000006400000000100CF40CF40CF30CF40CF30CF40CF40CF40CF30CF30CF40CF40CF30CF30CF40CF2060B320B2F0B340B2C0B3D0B4AFEF6CF386B65096D2700146D60626D606D606D606D6064CF320000100CF30CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF4060B330B320B2E0B340B410B48FEF9CF3F6B72096D2700146D60626D606D606D606D6064CFCC0000100CF40CF30CF40CF30CF40CF40CF30CF40CF30CF30CF30CF40CF30CF40CF30CF1060B330B2D0B2F0B340B3D0B48FF10CF646B7A096D2700146D60626D606D606D606D6064CFF70000100CF40CF30CF20CF20CF30CF20CF30CF10CF30CF30CF30CF20CF30CF30CF30CF1060B2D0B320B300B310B3C0B49FF11CF296B7F096D2A00136D60626D606D606D606D6064D0030000100CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF50CF40CF40CF40CF3060B310B2E0B310B2E0B400B4AFF1ACF4075580976EE00146D60636D606D606D606D6064CFD20000100CF30CF10CF40CF30CF30CF40CF30CF30CF10CF30CF40CF30CF30CF30CF30CF2060B300B2E0B2F0B330B3B0B42FF07CF636B50096D2400156D60626D606D606D606D6064CFCE0000100CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF40CF3060B2B0B2D0B290B2F0B3B0B4BFF1BCF3F6B7F096D2D00126D60626D606D606D606D6064D1260000100CF40CF40CF40CF40CF40CF40CF40CF60CF30CF40CF40CF40CF40CF40CF40CF3060B2A0B2E0B2D0B2A0B390B43FF24CF406B5F096D2700146D60626D606D606D606D6064D0C70000'

# 7e 32 32 30 31 34 41 30 30 32 30 41 34 30 31 30   ~22014A0020A4 01 0
# 30 36 34 31 34 43 37 31 30 30 43 46 39 30 43 46   064 14C7 10 0CF9 0CF
# 41 30 43 46 41 30 43 46 39 30 43 46 41 30 43 46   A 0CFA 0CF9 0CFA 0CF
# 44 30 43 46 45 30 44 30 30 30 43 46 45 30 43 46   D 0CFE 0D00 0CFE 0CF
# 42 30 43 46 44 30 44 30 31 30 43 46 46 30 44 30   B 0CFD 0D01 0CFF 0D0
# 31 30 43 46 42 30 43 46 45 30 30 44 32 30 30 42   1 0CFB 0CFE 00D2 00B
# 45 30 30 42 45 30 32 30 30 43 38 30 30 42 45 30   E 00BE 02 00C8 00BE 0
# 30 30 30 30 44 30 44 30 30 34 36 30 44 32 39 30   000 0D0D 0046 0D 290
# 42 32 39 30 42 30 30 32 46 30 30 30 30 30 30 30   B 290B 002F 00 00 00 0
# 30 30 30 30 30 30 30 30 30 30 38 32 33 30 30 30   0 00 00 00 00 08 23 00 0
# 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30   0 00 00 00 00 00 00 00 0
# 30 44 41 31 45 0d                                 0 DA1E.

      #22 01 4A 00 20 A4
#0-7  ] 01 00 64 14 C7 10 0C F9
#8-15 ] 0C FA 0C FA 0C F9 0C FA
#16-23] 0C FD 0C FE 0D 00 0C FE
#24-31] 0C FB 0C FD 0D 01 0C FF
#32-39] 0D 01 0C FB 0C FE 00 D2 00 BE 


    try:

        packs = int(inc_data[byte_index:byte_index+2],16)
        if print_initial:
            print("Packs: " + str(packs))
        byte_index = 2

        v_cell = {}
        t_cell = {}
        states = {}
        protections = ""
        alarms = ""
        state = ""

        for p in range(1,packs+1):

            if p > 1:
                cells_prev = cells

            soc.append(int(inc_data[byte_index:byte_index+4],16))
            byte_index += 4
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/soc",str(soc[p-1]))
            if print_initial:
               print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", SOC: " + str(soc[p-1]) + " %")

            v_pack.append(int(inc_data[byte_index:byte_index+4],16)/100)
            byte_index += 4
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/v_pack",str(v_pack[p-1]))
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", V Pack: " + str(v_pack[p-1]) + " V")

            cells = int(inc_data[byte_index:byte_index+2],16)

            print("cells: " +str(cells))

            #Possible remove this next test as were now testing for the INFOFLAG at the end
            if p > 1:
                if cells != cells_prev:
                    byte_index += 2
                    cells = int(inc_data[byte_index:byte_index+2],16)
                    if cells != cells_prev:
                        print("Error parsing BMS analog data: Cannot read multiple packs")
                        return(False,"Error parsing BMS analog data: Cannot read multiple packs")

            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", Total cells: " + str(cells))
            byte_index += 2

            cell_min_volt = 0
            cell_max_volt = 0

            for i in range(0,cells):
                v_cell[(p-1,i)] = int(inc_data[byte_index:byte_index+4],16)
                byte_index += 4
                client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/v_cells/cell_" + str(i+1).zfill(config['zero_pad_number_cells']) ,str(v_cell[(p-1,i)]))
                if print_initial:
                    print("Pack " + str(p).zfill(config['zero_pad_number_packs']) +", V Cell" + str(i+1).zfill(config['zero_pad_number_cells']) + ": " + str(v_cell[(p-1,i)]) + " mV")

                #Calculate cell max and min volt
                if i == 0:
                    cell_min_volt = v_cell[(p-1,i)]
                    cell_max_volt = v_cell[(p-1,i)]
                else:
                    if v_cell[(p-1,i)] < cell_min_volt:
                        cell_min_volt = v_cell[(p-1,i)]
                    if v_cell[(p-1,i)] > cell_max_volt:
                        cell_max_volt = v_cell[(p-1,i)]

            #Calculate cells max diff volt
            cell_max_diff_volt = cell_max_volt - cell_min_volt
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/cells_max_diff_calc" ,str(cell_max_diff_volt))
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) +", Cell Max Diff Volt Calc: " + str(cell_max_diff_volt) + " mV")

            t_mos= (int(inc_data[byte_index:byte_index+4],16))
            if t_mos > 32768:
                t_mos = t_mos - 65536
            t_mos = t_mos/10
            client.publish(config['mqtt_base_topic'] + "/t_mos",str(round(t_mos,1)))
            if print_initial:
               print("T Mos: " + str(t_mos) + " Deg")

            byte_index += 8 #Skip unknown temp in the middle
            t_env= (int(inc_data[byte_index:byte_index+4],16))
            if t_env > 32768:
               t_env = t_env - 65536
            t_env = t_env/10
            client.publish(config['mqtt_base_topic'] + "/t_env",str(round(t_env,1)))
            if print_initial:
               print("T Env: " + str(t_env) + " Deg")

            byte_index += 4
            temps = int(inc_data[byte_index:byte_index + 2],16)
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", Total temperature sensors: " + str(temps))

            byte_index += 2
            for i in range(0,temps): #temps-2
                tcell = int(inc_data[byte_index:byte_index + 4],16)
                if tcell > 32768:
                    tcell = tcell - 65536
                tcell = tcell/10
                t_cell[(p-1,i)] = tcell
                byte_index += 4
                client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/temps/temp_" + str(i+1) ,str(round(t_cell[(p-1,i)],1)))
                if print_initial:
                    print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", Temp" + str(i+1) + ": " + str(round(t_cell[(p-1,i)],1)) + " ℃")

            i_pack.append(int(inc_data[byte_index:byte_index+4],16))
            byte_index += 4
            if i_pack[p-1] >= 32768:
                i_pack[p-1] = -1*(65535 - i_pack[p-1])
            i_pack[p-1] = i_pack[p-1]/1000
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/i_pack",str(i_pack[p-1]))
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", I Pack: " + str(i_pack[p-1]) + " A")

            byte_index += 4 # Some voltage 33410??


            soh.append(int(inc_data[byte_index:byte_index+4],16))
            byte_index += 4
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/soh",str(soh[p-1]))
            if print_initial:
               print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", SOH: " + str(soh[p-1]) + " %")

            byte_index += 2 # Manual: Define number P = 3
            i_remain_cap.append(int(inc_data[byte_index:byte_index+4],16)/100)
            byte_index += 4
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/i_remain_cap",str(i_remain_cap[p-1]))
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", I Remaining Capacity: " + str(i_remain_cap[p-1]) + " Ah")

            #i_full_cap.append(int(inc_data[byte_index:byte_index+4],16)*10)
            #byte_index += 4
            #client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/i_full_cap",str(i_full_cap[p-1]))
            #if print_initial:
                #print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", I Full Capacity: " + str(i_full_cap[p-1]) + " mAh")

            i_design_cap.append(int(inc_data[byte_index:byte_index+4],16)/100)
            byte_index += 4
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/i_design_cap",str(i_design_cap[p-1]))
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", Design Capacity: " + str(i_design_cap[p-1]) + " Ah")

            cycles.append(int(inc_data[byte_index:byte_index+4],16))
            byte_index += 4
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/cycles",str(cycles[p-1]))
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", Cycles: " + str(cycles[p-1]))

            for i in range(20):
               states[p-1,i] = int(inc_data[byte_index:byte_index+2],16)
               byte_index += 2

            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/prot_short_circuit",str(states[p-1,3]>>3 & 1))
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/prot_discharge_current",str(states[p-1,3]>>4 & 3))
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/prot_charge_current",str(states[p-1,3]>>2 & 1))

            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/reverse",str(states[p-1,2]>>1 & 1))
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/current_limit",str(states[p-1,2]>>3 & 1))

            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/charge_fet",str(states[p-1,9] & 1))
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/discharge_fet",str(states[p-1,9]>>1 & 1))

            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/charging",str(states[p-1,3] & 1))
            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/discharging",str(states[p-1,3]>>1 & 1))

            if states[p-1,1] & 1 == 1:
                protections += "Cell Over Voltage. "
            if (states[p-1,1] >> 1) & 1 == 1:
                protections += "Cell Under Voltage. "
            if (states[p-1,1] >> 2) & 1 == 1:
                protections += "Pack Over Voltage. "
            if (states[p-1,1] >> 3) & 1 == 1:
                protections += "Pack Under Voltage. "
            if (states[p-1,1] >> 4) & 1 == 1:
                alarms += "Cell Over Voltage. "
            if (states[p-1,1] >> 5) & 1 == 1:
                alarms += "Cell Under Voltage. "
            if (states[p-1,1] >> 6) & 1 == 1:
                alarms += "Pack Over Voltage. "
            if (states[p-1,1] >> 7) & 1 == 1:
                alarms += "Pack Under Voltage. "
            if (states[p-1,0] >> 0) & 1 == 1:
                alarms += "Cell Voltage Difference. "
            if (states[p-1,0] >> 1) & 1 == 1:
                alarms += "Continuous over voltage (x10). "
            if (states[p-1,0] >> 2) & 1 == 1:
                alarms += "Continuous under voltage (x10). "
            if (states[p-1,0] >> 3) & 1 == 1:
                alarms += "Temperature Difference. "
            if (states[p-1,0] >> 7) & 1 == 1:
                state += "In Sleep State. "
            if (states[p-1,3] >> 2) & 1 == 1:
                protections += "Charging Over Current. "
            if (states[p-1,3] >> 3) & 1 == 1:
                protections += "Short Circuit. "
            if (states[p-1,3] >> 4) & 3 != 0:
                protections += "Discharge over current. "
            if (states[p-1,3] >> 6) & 1 != 0:
                alarms += "Charge over current. "
            if (states[p-1,3] >> 7) & 1 != 0:
                alarms += "Discharge over current. "
            if (states[p-1,2] >> 0) & 1 != 0:
                alarms += "Continuous over current (10x). "
            if (states[p-1,2] >> 1) & 1 == 1:
                protections += "Reverse connection. "
            if (states[p-1,2] >> 3) & 1 == 1:
                protections += "Current Limit. "
            if (states[p-1,5] >> 0) & 1 == 1:
                protections += "Charging Over Temp. "
            if (states[p-1,5] >> 1) & 1 == 1:
                protections += "Charging Under Temp. "
            if (states[p-1,5] >> 2) & 1 == 1:
                protections += "Discharging Over Temp. "
            if (states[p-1,5] >> 3) & 1 == 1:
                protections += "Disharging Under Temp. "
            if (states[p-1,5] >> 4) & 1 == 1:
                protections += "Ambient Over Temp. "
            if (states[p-1,5] >> 5) & 1 == 1:
                protections += "Ambient under Temp. "
            if (states[p-1,5] >> 6) & 1 == 1:
                protections += "MOS Over Temp. "
            if (states[p-1,5] >> 7) & 1 == 1:
                protections += "MOS under Temp. "
            if (states[p-1,4] >> 0) & 1 != 0:
                alarms += "Charge Over Temp. "
            if (states[p-1,4] >> 1) & 1 != 0:
                alarms += "Charge Under Temp. "
            if (states[p-1,4] >> 2) & 1 != 0:
                alarms += "Discharge Over Temp. "
            if (states[p-1,4] >> 3) & 1 != 0:
                alarms += "Discharge Under Temp. "
            if (states[p-1,4] >> 4) & 1 != 0:
                alarms += "Ambient Over Temp. "
            if (states[p-1,4] >> 5) & 1 != 0:
                alarms += "Ambient Under Temp. "
            if (states[p-1,4] >> 6) & 1 != 0:
                alarms += "MOS Over Temp. "
            if (states[p-1,4] >> 7) & 1 != 0:
                alarms += "MOS Under Temp. "
            if (states[p-1,7] >> 0) & 1 == 1:
                state += "System Power On. "
            if (states[p-1,7] >> 1) & 1 != 0:
                alarms += "Charge FET damage. "
            if (states[p-1,7] >> 2) & 1 != 0:
                alarms += "SD Card Fail. "
            if (states[p-1,7] >> 3) & 1 != 0:
                alarms += "SPI Comms Fail. "
            if (states[p-1,7] >> 4) & 1 != 0:
                alarms += "EEPROM Fail. "
            if (states[p-1,7] >> 5) & 1 != 0:
                state += "LED alarm enabled. "
            if (states[p-1,7] >> 6) & 1 != 0:
                state += "Buzzer alarm enabled. "
            if (states[p-1,7] >> 7) & 1 != 0:
                alarms += "Low Battery. "
            if (states[p-1,6] >> 1) & 1 != 0:
                alarms += "Heating film damaged. "
            if (states[p-1,6] >> 2) & 1 != 0:
                alarms += "Current Limit Board damaged. "
            if (states[p-1,6] >> 3) & 1 != 0:
                alarms += "Sampling failure. "
            if (states[p-1,6] >> 4) & 1 != 0:
                alarms += "Battery failure. "
            if (states[p-1,6] >> 5) & 1 != 0:
                alarms += "NTC failure. "
            if (states[p-1,6] >> 6) & 1 != 0:
                alarms += "Charge MOS failure. "
            if (states[p-1,6] >> 7) & 1 != 0:
                alarms += "Discharge MOS failure. "

            if (states[p-1,9] >> 2) & 1 != 0:
                state += "Discharge MOS OK. "
            if (states[p-1,9] >> 3) & 1 != 0:
                state += "Charge MOS OK. "

            c_l = (states[p-1,9] & 0x30) >> 4
            if c_l == 0:
               state += "No Current Limit. "
            if c_l == 1:
               state += "20A Current Limit. "
            if c_l == 2:
               state += "10A Current Limit. "
            if c_l == 3:
               state += "25A Current Limit. "

            if (states[p-1,9] >> 6) & 1 != 0:
                state += "Heating Film On. "
            if (states[p-1,9] >> 7) & 1 != 0:
                state += "Constant Current State. "
            if (states[p-1,8] >> 0) & 1 != 0:
                state += "No Fully State. "
            if (states[p-1,8] >> 1) & 1 != 0:
                state += "No AC In State. "
            if (states[p-1,8] >> 2) & 1 != 0:
                state += "Pack Not Powered State. "
            if (states[p-1,8] >> 3) & 1 != 0:
                state += "LED Alarm ON State. "
            if (states[p-1,8] >> 4) & 1 != 0:
                state += "Buzzer ON State. "
            if (states[p-1,8] >> 5) & 1 != 0:
                state += "AFE Chip Failure. "


            balanceState = '{0:016b}'.format(int(states[p-1,18]*256 + states[p-1,19]))

            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/states",state)
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", states: " + state)

            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/alarms",alarms)
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", alarms: " + alarms)

            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/protections",protections)
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", protections: " + protections)

            client.publish(config['mqtt_base_topic'] + "/pack_" + str(p).zfill(config['zero_pad_number_packs']) + "/balancing",balanceState)
            if print_initial:
                print("Pack " + str(p).zfill(config['zero_pad_number_packs']) + ", balancing: " + balanceState)

            byte_index += int(config['force_pack_offset'])
            #Test for non signed value (matching cell count), to skip possible INFOFLAG present in data
            if p < packs: #Test - Is there more packs to read?
                while (byte_index < len(inc_data)) and (cells != int(inc_data[byte_index:byte_index+2],16)):
                    byte_index += 2
                    if byte_index > len(inc_data):
                        print("Error parsing BMS analog data: Cannot read multiple packs")
                        return(False,"Error parsing BMS analog data: Cannot read multiple packs")


    except Exception as e:
        print("Error parsing BMS analog data: ", str(e))
        return(False,"Error parsing BMS analog data: " + str(e))

    if print_initial:
        print("Script running....")

    return True,True

print("Connecting to BMS...")
bms,bms_connected = bms_connect(config['bms_ip'],config['bms_port'])

client.publish(config['mqtt_base_topic'] + "/availability","offline")
print_initial = True

#success, data = bms_getVersion(bms)
#if success != True:
#    print("Error retrieving BMS version number")

#time.sleep(0.1)
success, bms_sn,pack_sn = bms_getSerial(bms)

if success != True:
    print("Error retrieving BMS and pack serial numbers. This is required for HA Discovery. Exiting...")
    quit()

while code_running == True:

    if bms_connected == True:
        if mqtt_connected == True:

            success, data = bms_getData(bms,batNumber=255)
            if success != True:
                print("Error retrieving BMS analog data: " + data)
            time.sleep(scan_interval)

            if print_initial:
                ha_discovery()

            client.publish(config['mqtt_base_topic'] + "/availability","online")

            print_initial = False

            repub_discovery += 1
            if repub_discovery*scan_interval > 3600:
                repub_discovery = 0
                print_initial = True

        else: #MQTT not connected
            client.loop_stop()
            print("MQTT disconnected, trying to reconnect...")
            client.connect(config['mqtt_host'], config['mqtt_port'], 60)
            client.loop_start()
            time.sleep(5)
            print_initial = True
    else: #BMS not connected
        print("BMS disconnected, trying to reconnect...")
        bms,bms_connected = bms_connect(config['bms_ip'],config['bms_port'])
        client.publish(config['mqtt_base_topic'] + "/availability","offline")
        time.sleep(5)
        print_initial = True

client.loop_stop()
