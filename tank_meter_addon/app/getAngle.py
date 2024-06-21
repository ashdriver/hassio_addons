import cv2
import numpy as np
import paho.mqtt.client as mqtt
import sys
import datetime;
import json
import os
import logging
import sys

print("Dial analysis app started.")

LOG_LEVEL = os.environ['LOG_LEVEL']
MQTT_SERVER = "10.0.0.77"
MQTT_SERVER = os.environ['MQTT_HOST']
MQTT_PORT = 1883
try:
    MQTT_PORT = int(os.environ['MQTT_PORT'])
except:
    pass
MQTT_USER = os.environ['MQTT_USERNAME']
MQTT_PASS = os.environ['MQTT_PASSWORD']

CENTRE_X = int(os.environ['CENTRE_X'])
CENTRE_Y = int(os.environ['CENTRE_Y'])


innerInnerRadius = 110
outerInnerRadius = 130

innerOuterRadius = 180
outerOuterRadius = 200

OUTPUT_DIR = "/config/www/dialDebugImages/"

def writeDebugImage(imageName,imageData):
    TS = datetime.datetime.now().strftime("%H%M-%y%m%d")
    try:
        os.mkdir(OUTPUT_DIR + TS)
    except:
        pass
    cv2.imwrite(OUTPUT_DIR + TS + "/" +  imageName, imageData)
    cv2.imwrite('/config/www/' + imageName, imageData)


def getAngle(image,debug):
    originalImage = image.copy()
    if debug:
        writeDebugImage('inputImage.jpg', image)

    testExposure = image[500:600,700:800].copy()
    hsv = cv2.cvtColor(testExposure, cv2.COLOR_RGB2HSV)
    brightness = np.sum(hsv[:,:, 2])
    pxl = 100 * 800
    averageBright = brightness / pxl
    if (averageBright < 12):
        log.error(">>> Brightness too low: " + str(averageBright))
        return
    logging.debug("Brightness OK: " + str(averageBright))


    grayIn = cv2.cvtColor(originalImage, cv2.COLOR_BGR2GRAY)
    _,otsuFullImage = cv2.threshold(grayIn,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    otsuFullImage = cv2.bitwise_not(otsuFullImage)
    if debug:
        writeDebugImage('Thresholded.jpg', otsuFullImage)

    # Donut:
    hh, ww = otsuFullImage.shape[:2]

    # define circles
    xc = CENTRE_X
    yc = CENTRE_Y

    log.debug("hh " + str(hh) + " ww: " + str(ww) + " xc: " + str(xc) + " yc: " + str(yc))

    # draw filled circles in white on black background as masks
    mask1 = np.zeros_like(otsuFullImage)
    mask1 = cv2.circle(mask1, (xc,yc), innerInnerRadius, 255, -1)
    mask2 = np.zeros_like(otsuFullImage)
    mask2 = cv2.circle(mask2, (xc,yc), outerInnerRadius, 255, -1)

    # subtract masks and make into single channel
    innerdonutMask = cv2.subtract(mask2, mask1)

    mask1 = np.zeros_like(otsuFullImage)
    mask1 = cv2.circle(mask1, (xc,yc), innerOuterRadius, 255, -1)
    mask2 = np.zeros_like(otsuFullImage)
    mask2 = cv2.circle(mask2, (xc,yc), outerOuterRadius, 255, -1)

    outerdonutMask = cv2.subtract(mask2, mask1)

    maskedInner = cv2.bitwise_and(innerdonutMask, otsuFullImage)
    maskedOuter = cv2.bitwise_and(outerdonutMask, otsuFullImage)

    if debug:
        writeDebugImage('innerdonut.jpg', maskedInner)
        writeDebugImage('outerdonut.jpg', maskedOuter)

    innerAngle = -1000

    # Find inner contours
    contours, _ = cv2.findContours(maskedInner, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    #Colour image to dispay contours with.
    if (len(contours)  != 1):
        log.warning("GOT " + str(len(contours)) + " INNER CONTOURS!")
        if (len(contours) > 2) :
            log.warning(">>>>>> Skipping this round - too many inner contours (>2)).")
            TS = datetime.datetime.now().strftime("%H%M-%y%m%d")
            try:
                os.mkdir(OUTPUT_DIR + "BAD/")
            except:
                pass
            cv2.imwrite(OUTPUT_DIR + "BAD/"  +  TS+".jpg", originalImage)            
            return
        
    if debug:
        ContoursInner = cv2.cvtColor(maskedInner, cv2.COLOR_GRAY2BGR)
        cv2.drawContours(ContoursInner, contours, -1, (0,255,0), 3)        
        writeDebugImage('outputIn.jpg', ContoursInner)

    
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 60 or area > 1000:
            log.error(">>> BAD INNER AREA: " + str(area) )
            continue
        M = cv2.moments(contour)
        try:
            cx = int(M['m10']/M['m00'])
        except:
            log.error("BAD INNER CENTROID: " + str(M['m10']) + " x " + str(M['m00']))
            continue
        try:
            cy = int(M['m01']/M['m00'])
        except:
            log.error("BAD INNER CENTROID: " + str(M['m10']) + " x " + str(M['m00']))
            continue

        dx = CENTRE_X - cx
        dy = CENTRE_Y - cy

        innerAngle = (90+360 + (np.arctan2(dy, dx) * 180 / np.pi)) % 360
        log.debug("Inner Centroid: " + str(cx) + " x " + str(cy) + ". Got an inner region, area: " + str(area))

    if (innerAngle == -1000):
        log.warning("No inner region found.")


    # Find outer contours
    contours, _ = cv2.findContours(maskedOuter, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    log.debug("Got " + str(len(contours)) + " outer contours")

    if debug:
        ContoursOuter = cv2.cvtColor(maskedOuter, cv2.COLOR_GRAY2BGR)
        cv2.drawContours(ContoursOuter, contours, -1, (0,255,0), 3)
        writeDebugImage('outputOut.jpg', ContoursOuter)

    cox = 0
    coy = 0

    outerAngle = -1

    if innerAngle == -1000 :
        if len(contours) != 1 :
            log.warning(">>>>>> Skipping this round - no inner found and no single outer found (" + str(len(contours)) + ")")
            TS = datetime.datetime.now().strftime("%H%M-%y%m%d")
            try:
                os.mkdir(OUTPUT_DIR + "BAD/")
            except:
                pass
            cv2.imwrite(OUTPUT_DIR + "BAD/"  +  TS+".jpg", originalImage)            
            return
        else:
            log.warning("No Inner found - using single outer only")

    for contour in contours:
        if area < 60 or area > 1200:
            log.error(">>> BAD OUTER AREA: " + str(area) )
            continue        
        M = cv2.moments(contour)
        try:
            cox = int(M['m10']/M['m00'])
        except:
            log.error("BAD OUTER CENTROID: " + str(M['m10']) + " x " + str(M['m00']) )
            continue

        try:
            coy = int(M['m01']/M['m00'])
        except:
            log.error("BAD OUTER CENTROID: " + str(M['m10']) + " x " + str(M['m00']) )
            continue
        area = cv2.contourArea(contour)
        log.debug( "Outer Centroid: " + str(cox) + " x " + str(coy) + " Area: " + str(area))

        dx = CENTRE_X - cox
        dy = CENTRE_Y - coy

        outerAngle = (90+360 + (np.arctan2(dy, dx) * 180 / np.pi)) % 360
        if ((outerAngle-4) < innerAngle < (outerAngle+4) or innerAngle == -1000):
            break
        else:
            log.warning(">>> Skipping outer contour, out of bounds! Angle: " + str(outerAngle))
            outerAngle = -1

    finalAngle = outerAngle
    if outerAngle == -1:
        if innerAngle == -1000:
            # Means no inner and single outer was bad.
            log.warning(">>>>>> Skipping this round - no inner found single outer was bad")
            TS = datetime.datetime.now().strftime("%H%M-%y%m%d")
            try:
                os.mkdir(OUTPUT_DIR + "BAD/")
            except:
                pass
            cv2.imwrite(OUTPUT_DIR + "BAD/"  +  TS+".jpg", originalImage)
            return        
        finalAngle = innerAngle
        cox = cx
        coy = cy
        log.info("No outer Angle found, using inner")
    else:
        log.info("Outer Angle found " + str(outerAngle))

    if debug:
        originalImage = cv2.bitwise_or(ContoursOuter,originalImage)
        originalImage = cv2.bitwise_or(ContoursInner,originalImage)
        cv2.line(originalImage, (CENTRE_X,CENTRE_Y), (cox,coy), (255,50,50), 2)
        cv2.line(originalImage, (cox,coy),(2*cox - CENTRE_X,2*coy - CENTRE_Y), (255,50,255), 2)
        cv2.line(originalImage, (cx-5,cy-5), (cx+5,cy+5), (50,50,255), 2)
        cv2.line(originalImage, (cx-5,cy+5), (cx+5,cy-5), (50,50,255), 2)        
        writeDebugImage('finalAngle.jpg', originalImage)

    innerAngle = round(innerAngle,2)
    outerAngle = round(outerAngle,2)
    finalAngle = round(finalAngle,2)

    log.info(">>>>>>>>>>>>>> INNER:" + str(innerAngle) + " OUTER:" + str(outerAngle) + " FINAL:" + str(finalAngle))

    (rc,_) = client.publish("tankdial/result", str(finalAngle), qos=1)

    if rc != 0:
        log.error("Publish Error rc: " + str(rc))


def image_ready(client, userdata, msg):
    image = cv2.imread('/config/www/tankmeter1.jpg')
    if image is None:
        log.error("Could not open image")
        return
    if LOG_LEVEL == "DEBUG":
        getAngle(image, True)
    else:
        getAngle(image, False)

try:
    os.mkdir(OUTPUT_DIR)
except:
    pass

file_handler = logging.handlers.WatchedFileHandler(filename='/config/www/dial.log')
stdout_handler = logging.StreamHandler(stream=sys.stdout)
handlers = [file_handler, stdout_handler]

logLevel = logging.ERROR
if  LOG_LEVEL == "INFO" :
    logLevel = logging.INFO
if  LOG_LEVEL == "DEBUG" :
    logLevel = logging.DEBUG
if  LOG_LEVEL == "WARNING" :
    logLevel = logging.WARNING


logging.basicConfig(
    level=logLevel,
    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
    handlers=handlers
)

log = logging.getLogger()

log.info("App Started.")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(MQTT_SERVER, MQTT_PORT)

client.on_message=image_ready

autoDiscoverPayload ={  "~": "tankdial","unit_of_measurement":"degrees","device_class":"volume_storage","state_class": "measurement","state_topic":"~/result","name":"Rain Tank Level Dial Angle","unique_id":"raintank_dialangle","device":{"identifiers":["tankdial"],"name":"Rain Tank",}}
client.publish("homeassistant/sensor/tankdial/result/config", json.dumps(autoDiscoverPayload),  retain=True)

client.subscribe("tankdial/image_ready")

client.loop_forever()
