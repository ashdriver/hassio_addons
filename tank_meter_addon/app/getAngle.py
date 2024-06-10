import cv2
import numpy as np
import paho.mqtt.client as mqtt
import sys
import datetime;
import json
 


LOG_LEVEL = sys.argv[5]
if LOG_LEVEL == "DEBUG":
    print(sys.argv)

MQTT_SERVER = "10.0.0.77"
MQTT_SERVER = sys.argv[1]
MQTT_PORT = 1883
try:
    MQTT_PORT = int(sys.argv[2])
except:
    pass
MQTT_USER = sys.argv[3]
MQTT_PASS = sys.argv[4]

CENTER_X = 398
CENTER_Y = 247

mask_color = [135,160,150]

diff = 7 # How much more red before masking
clipLevel = 120 # how bright before masking 
contrastThreshold = 140


def getAngle(image,debug):
    height, width, channels = np.shape(image)
    mask = np.zeros((height,width))
    # iterate over all pixels in the image and assign 0 to the mask(x,y) if image(x,y) has channels==old_color
    mask= [[ 1  if channels[2] > (channels[1] + diff) or (channels[2] > channels[0] + diff) else 0 for channels in row ] for row in image ] 
    mask = np.array(mask)

    coords_x, coord_y = np.where(mask>0)

    image[coords_x,coord_y,:]=mask_color
    if debug:
        cv2.imwrite('/config/www/mask.jpg', image)

    #gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    #adjusted = cv2.convertScaleAbs(image, alpha=1.0, beta=0)

    #image = adjusted


    mask= [[ 0  if channels[2] < clipLevel or channels[1] < clipLevel or channels[0] < clipLevel else 1 for channels in row ] for row in image ]
    mask = np.array(mask)
    coords_x, coord_y = np.where(mask>0)
    image[coords_x,coord_y,:]=mask_color

    if debug:
        cv2.imwrite('/config/www/cmask.jpg', image)

    # Donut:
    hh, ww = image.shape[:2]



    # define circles
    radius1 = 75
    radius2 = 95
    xc = CENTER_X
    yc = CENTER_Y

    if debug:
        print("hh " + str(hh) + " ww: " + str(ww) + " xc: " + str(xc) + " yc: " + str(yc))

    # draw filled circles in white on black background as masks
    mask1 = np.zeros_like(image)
    mask1 = cv2.circle(mask1, (xc,yc), radius1, (255,255,255), -1)
    mask2 = np.zeros_like(image)
    mask2 = cv2.circle(mask2, (xc,yc), radius2, (255,255,255), -1)

    # subtract masks and make into single channel
    innerdonut = cv2.subtract(mask2, mask1)

    radius3 = 140
    radius4 = 200

    mask1 = np.zeros_like(image)
    mask1 = cv2.circle(mask1, (xc,yc), radius3, (255,255,255), -1)
    mask2 = np.zeros_like(image)
    mask2 = cv2.circle(mask2, (xc,yc), radius4, (255,255,255), -1)

    outerdonut = cv2.subtract(mask2, mask1)

    maskedInner = cv2.bitwise_and(innerdonut, image)
    maskedOuter = cv2.bitwise_and(outerdonut, image)

    if debug:
        cv2.imwrite('/config/www/innerdonut.jpg', maskedInner)
        cv2.imwrite('/config/www/outerdonut.jpg', maskedOuter)

    # Convert to grayscale
    grayIn = cv2.cvtColor(maskedInner, cv2.COLOR_BGR2GRAY)
    grayOut = cv2.cvtColor(maskedOuter, cv2.COLOR_BGR2GRAY)

    invedgesIn = cv2.bitwise_not(grayIn)
    invedgesOut = cv2.bitwise_not(grayOut)

    mask1 = np.zeros_like(invedgesIn)
    mask1 = cv2.circle(mask1, (xc,yc), radius1, (255,255,255), -1)
    mask2 = np.zeros_like(invedgesIn)
    mask2 = cv2.circle(mask2, (xc,yc), radius2, (255,255,255), -1)

    # subtract masks and make into single channel
    innerdonut = cv2.subtract(mask2, mask1)

    mask1 = np.zeros_like(invedgesOut)
    mask1 = cv2.circle(mask1, (xc,yc), radius3, (255,255,255), -1)
    mask2 = np.zeros_like(invedgesOut)
    mask2 = cv2.circle(mask2, (xc,yc), radius4, (255,255,255), -1)

    outerdonut = cv2.subtract(mask2, mask1)

    maskIn =  cv2.bitwise_and(innerdonut, invedgesIn)
    maskOut =  cv2.bitwise_and(outerdonut, invedgesOut)

    ret,contrastIn = cv2.threshold(maskIn,contrastThreshold,255,cv2.THRESH_BINARY)

    if debug:
        #cv2.imwrite('edges.jpg', edges)
        cv2.imwrite('contrastin.jpg', contrastIn)

    ret,contrastOut = cv2.threshold(maskOut,contrastThreshold,255,cv2.THRESH_BINARY)

    if debug:
        cv2.imwrite('/config/www/contrastOut.jpg', contrastOut)

    # Find contours
    contours, _ = cv2.findContours(contrastIn.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    # Sort contours by area and find the largest contour
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:1]
    if debug:
        print("Got " + str(len(contours)) + " inner contours")
    ContourIn = cv2.cvtColor(contrastIn, cv2.COLOR_GRAY2BGR)
    cv2.drawContours(ContourIn, contours, -1, (0,255,0), 3)
    for contour in contours:
        # Approximate the contour

        M = cv2.moments(contour)
        cx = int(M['m10']/M['m00'])
        cy = int(M['m01']/M['m00'])
        if debug:
            print( "Centroid: " + str(cx) + " x " + str(cy) )

        dx = CENTER_X - cx
        dy = CENTER_Y - cy

        innerAngle = (90+360 + (np.arctan2(dy, dx) * 180 / np.pi)) % 360
        if debug:
            print("Angle of the dial:", innerAngle)
        if LOG_LEVEL == "INFO":
            print("Inner angle: " + str(innerAngle))

    if debug:
        cv2.imwrite('outputIn.jpg', ContourIn)

    # Find contours
    contours, _ = cv2.findContours(contrastOut.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if debug:
        print("Got " + str(len(contours)) + " outer contours")
    contourOut = cv2.cvtColor(contrastOut, cv2.COLOR_GRAY2BGR)
    cv2.drawContours(contourOut, contours, -1, (0,255,0), 3)
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

        outerAngle = -1
        if debug:
            print("Angles " + str(smallestAngle) + " <> " + str(largestAngle))

        if (smallestAngle < innerAngle < largestAngle ):
            if debug:
                print("GOT BOUND CONTOUR ON OUTER! " + str(innerAngle) + " between " + str(smallestAngle) + " and " + str(largestAngle))

            M = cv2.moments(contour)
            cx = int(M['m10']/M['m00'])
            cy = int(M['m01']/M['m00'])
            if debug:
                print( "Centroid: " + str(cx) + " x " + str(cy) )

            dx = CENTER_X - cx
            dy = CENTER_Y - cy


            outerAngle = (90+360 + (np.arctan2(dy, dx) * 180 / np.pi)) % 360
            if debug:
                print("Outer Angle of the dial:", outerAngle)

            # Draw a rectangle around the contour
            cv2.rectangle(contourOut, (x, y), (x + w, y + h), (0, 255, 0), 2)

            break

    finalAngle = outerAngle
    if outerAngle == -1:
        finalAngle = innerAngle
        if LOG_LEVEL == "INFO":
            print("No outer Angle found")
    else:
        if LOG_LEVEL == "INFO":
            print("Outer Angle found ", outerAngle)

    if debug:
        print(str (datetime.datetime.now()) + "] Final Angle of the dial:", finalAngle)
        cv2.imwrite('/config/www/outputOut.jpg', contourOut)

    (rc,_) = client.publish("homeassistant/tankdial/result", str(finalAngle), qos=1)

    if rc != 0:
        print("Publish Error rc: " + str(rc))


def image_ready(client, userdata, msg):
    image = cv2.imread('/config/www/tankmeter1.jpg')
    if LOG_LEVEL == "DEBUG":
        getAngle(image, True)
    else:
        getAngle(image, False)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(MQTT_SERVER, MQTT_PORT)

client.on_message=image_ready

client.subscribe("homeassistant/tankdial/image_ready")

client.loop_forever()
