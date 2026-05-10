ARG BUILD_FROM
FROM $BUILD_FROM

RUN apt update
RUN apt-get install python3 -y python3-pip -y python3-venv -y 
WORKDIR /app
RUN python3 -m venv /app/venv/appenv
RUN source /app/venv/appenv/bin/activate



ENV VIRTUAL_ENV=/root/venv/day_ahead
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip3 install opencv-python-headless
RUN pip3 install paho-mqtt

ADD ./app /app

# Copy data for add-on
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
#CMD [ "/bin/bash" ]

