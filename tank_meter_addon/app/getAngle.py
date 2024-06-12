import cv2
import numpy as np
import paho.mqtt.client as mqtt
import sys
import datetime;
import json
import os
import logging
import sys

LOG_LEVEL = sys.argv[8]
MQTT_SERVER = "10.0.0.77"
MQTT_SERVER = sys.argv[4]
MQTT_PORT = 1883
try:
    MQTT_PORT = int(sys.argv[5])
except:
    pass
MQTT_USER = sys.argv[6]
MQTT_PASS = sys.argv[7]

CENTER_X = int(sys.argv[1])
CENTER_Y = int(sys.argv[2])

mask_color = [135,160,150]

diff = 7 # How much more red before masking
clipLevel = 110 # how bright before masking 
contrastThreshold = int(sys.argv[3])

innerInnerRadius = 80
outerInnerRadius = 95

innerOuterRadius = 140
outerOuterRadius = 200

OUTPUT_DIR = "/config/www/dialDebugImages/"

def writeDebugImage(imageName,imageData):
    TS = datetime.datetime.now().strftime("%H:%M-%y-%m-%d")
    try:
        os.mkdir(OUTPUT_DIR + TS)
    except:
        pass
    cv2.imwrite(OUTPUT_DIR + TS + "/" +  imageName, imageData)
    cv2.imwrite('/config/www/' + imageName, imageData)


def getAngle(image,debug):
    originalImage = image.copy()
    height, width, channels = np.shape(image)
    mask = np.zeros((height,width))
    # iterate over all pixels in the image and assign 0 to the mask(x,y) if image(x,y) has channels==old_color
    mask= [[ 1  if channels[2] > (channels[1] + diff) or (channels[2] > channels[0] + diff) else 0 for channels in row ] for row in image ] 
    mask = np.array(mask)

    coords_x, coord_y = np.where(mask>0)

    image[coords_x,coord_y,:]=mask_color
    if debug:
        writeDebugImage('maskred.jpg', image)

    mask= [[ 0  if channels[2] < clipLevel or channels[1] < clipLevel or channels[0] < clipLevel else 1 for channels in row ] for row in image ]
    mask = np.array(mask)
    coords_x, coord_y = np.where(mask>0)
    image[coords_x,coord_y,:]=mask_color

    if debug:
        writeDebugImage('maskbright.jpg', image)

    # Donut:
    hh, ww = image.shape[:2]

    # define circles
    xc = CENTER_X
    yc = CENTER_Y

    log.debug("hh " + str(hh) + " ww: " + str(ww) + " xc: " + str(xc) + " yc: " + str(yc))

    # draw filled circles in white on black background as masks
    mask1 = np.zeros_like(image)
    mask1 = cv2.circle(mask1, (xc,yc), innerInnerRadius, (255,255,255), -1)
    mask2 = np.zeros_like(image)
    mask2 = cv2.circle(mask2, (xc,yc), outerInnerRadius, (255,255,255), -1)

    # subtract masks and make into single channel
    innerdonut = cv2.subtract(mask2, mask1)

    mask1 = np.zeros_like(image)
    mask1 = cv2.circle(mask1, (xc,yc), innerOuterRadius, (255,255,255), -1)
    mask2 = np.zeros_like(image)
    mask2 = cv2.circle(mask2, (xc,yc), outerOuterRadius, (255,255,255), -1)

    outerdonut = cv2.subtract(mask2, mask1)

    maskedInner = cv2.bitwise_and(innerdonut, image)
    maskedOuter = cv2.bitwise_and(outerdonut, image)

    if debug:
        writeDebugImage('innerdonut.jpg', maskedInner)
        writeDebugImage('outerdonut.jpg', maskedOuter)

    # Convert to grayscale
    grayIn = cv2.cvtColor(maskedInner, cv2.COLOR_BGR2GRAY)
    grayOut = cv2.cvtColor(maskedOuter, cv2.COLOR_BGR2GRAY)

    invedgesIn = cv2.bitwise_not(grayIn)
    invedgesOut = cv2.bitwise_not(grayOut)

    mask1 = np.zeros_like(invedgesIn)
    mask1 = cv2.circle(mask1, (xc,yc), innerInnerRadius, (255,255,255), -1)
    mask2 = np.zeros_like(invedgesIn)
    mask2 = cv2.circle(mask2, (xc,yc), outerInnerRadius, (255,255,255), -1)

    # subtract masks and make into single channel
    innerdonut = cv2.subtract(mask2, mask1)

    mask1 = np.zeros_like(invedgesOut)
    mask1 = cv2.circle(mask1, (xc,yc), innerOuterRadius, (255,255,255), -1)
    mask2 = np.zeros_like(invedgesOut)
    mask2 = cv2.circle(mask2, (xc,yc), outerOuterRadius, (255,255,255), -1)

    outerdonut = cv2.subtract(mask2, mask1)

    maskIn =  cv2.bitwise_and(innerdonut, invedgesIn)
    maskOut =  cv2.bitwise_and(outerdonut, invedgesOut)

    _,contrastIn = cv2.threshold(maskIn,contrastThreshold,255,cv2.THRESH_BINARY)

    _,contrastOut = cv2.threshold(maskOut,contrastThreshold,255,cv2.THRESH_BINARY)

    if debug:
        writeDebugImage('contrastIn.jpg', contrastIn)
        writeDebugImage('contrastOut.jpg', contrastOut)

    # Find contours
    contours, _ = cv2.findContours(contrastIn.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    # Sort contours by area and find the largest contour
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:1]
    log.debug("Got " + str(len(contours)) + " inner contours")
    ContourIn = cv2.cvtColor(contrastIn, cv2.COLOR_GRAY2BGR)
    cv2.drawContours(ContourIn, contours, -1, (0,255,0), 3)
    innerAngle = 0
    cx = 0
    cy = 0
    for contour in contours:
        M = cv2.moments(contour)
        try:
            cx = int(M['m10']/M['m00'])
        except:
            log.error("BAD INNER CENTROID: " + str(M['m10']) + " x " + str(M['m00']))
            cx = 0
        try:
            cy = int(M['m01']/M['m00'])
        except:
            log.error("BAD INNER CENTROID: " + str(M['m10']) + " x " + str(M['m00']))
            cy = -1000

        dx = CENTER_X - cx
        dy = CENTER_Y - cy

        innerAngle = (90+360 + (np.arctan2(dy, dx) * 180 / np.pi)) % 360
        log.debug("Inner Centroid: " + str(cx) + " x " + str(cy) )        
        log.info("Inner angle: " + str(innerAngle))

    if debug:
        writeDebugImage('outputIn.jpg', ContourIn)

    # Find contours
    contours, _ = cv2.findContours(contrastOut.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    log.debug("Got " + str(len(contours)) + " outer contours")
    contourOut = cv2.cvtColor(contrastOut, cv2.COLOR_GRAY2BGR)
    cv2.drawContours(contourOut, contours, -1, (0,255,0), 3)

    cox = 0
    coy = 0

    outerAngle = -1

    for contour in contours:
        # Approximate the contour
        #peri = cv2.arcLength(contour, True)
        #approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
    #    print("Got " + str(len(approx)) + " vertices")

        # Get the bounding box of the contour
        (x, y, w, h) = cv2.boundingRect(contour)
    #    print("Bounding box: " + str(x) + " x " + str(y) + " w " + str(w) + " h " + str(h))

        boundingAngles = []
        dx = CENTER_X - x
        dy = CENTER_Y - (y+h)
        boundingAngles.append( 90 + np.arctan2(dy, dx) * 180 / np.pi)

        dx = CENTER_X - x
        dy = CENTER_Y - y
        boundingAngles.append(90 + np.arctan2(dy, dx) * 180 / np.pi)
        dx = CENTER_X - (x+w)
        dy = CENTER_Y - y
        boundingAngles.append( 90 + np.arctan2(dy, dx) * 180 / np.pi)
        dx = CENTER_X - (x+w)
        dy = CENTER_Y - (y+h)
        boundingAngles.append( 90 + np.arctan2(dy, dx) * 180 / np.pi)

        for idx, angle in enumerate(boundingAngles):
            if (angle<0):
                boundingAngles[idx] = 360 + angle

        boundingAngles.sort()

        smallestAngle = boundingAngles[0]
        largestAngle = boundingAngles[-1]
        if (largestAngle - smallestAngle > 180):
            if innerAngle > 180:
                largestAngle = smallestAngle + 360
                smallestAngle = boundingAngles[-1]
            else:
                smallestAngle = largestAngle - 360
                largestAngle = boundingAngles[0]

        log.debug("Angles " + str(smallestAngle) + " <> " + str(largestAngle))

        if (smallestAngle < innerAngle < largestAngle ):
            log.debug("GOT BOUND CONTOUR ON OUTER! " + str(innerAngle) + " between " + str(smallestAngle) + " and " + str(largestAngle))

            M = cv2.moments(contour)
            try:
                cox = int(M['m10']/M['m00'])
            except:
                log.error("BAD OUTER CENTROID: " + str(M['m10']) + " x " + str(M['m00']))
                cox = 0

            try:
                coy = int(M['m01']/M['m00'])
            except:
                log.error("BAD OUTER CENTROID: " + str(M['m10']) + " x " + str(M['m00']))
                coy = -1000
                
            log.debug( "Outer Centroid: " + str(cox) + " x " + str(coy) )

            dx = CENTER_X - cox
            dy = CENTER_Y - coy

            outerAngle = (90+360 + (np.arctan2(dy, dx) * 180 / np.pi)) % 360
            log.debug("Outer Angle of the dial:" + str(outerAngle))

            # Draw a rectangle around the contour
#            cv2.rectangle(contourOut, (x, y), (x + w, y + h), (0, 255, 0), 2)

            break

    finalAngle = outerAngle
    if outerAngle == -1:
        finalAngle = innerAngle
        cox = cx
        coy = cy
        log.info("No outer Angle found")
    else:
        log.info("Outer Angle found " + str(outerAngle))

    if debug:
        writeDebugImage('outputOut.jpg', contourOut)
        cv2.line(originalImage, (CENTER_X,CENTER_Y), (cox,coy), (255,50,50), 2) 
        cv2.line(originalImage, (cox,coy),(2*cox - CENTER_X,2*coy - CENTER_Y), (255,50,255), 2)        
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

file_handler = logging.FileHandler(filename='/config/www/dial.log')
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
log.debug(sys.argv)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(MQTT_SERVER, MQTT_PORT)

client.on_message=image_ready

autoDiscoverPayload ={  "~": "tankdial","unit_of_measurement":"degrees","device_class":"volume_storage","state_class": "measurement","state_topic":"~/result","name":"Rain Tank Level Dial Angle","unique_id":"raintank_dialangle","device":{"identifiers":["tankdial"],"name":"Rain Tank",}}
client.publish("homeassistant/sensor/tankdial/result/config", json.dumps(autoDiscoverPayload),  retain=True)

client.subscribe("tankdial/image_ready")

client.loop_forever()
