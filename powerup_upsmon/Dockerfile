ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk update && apk add --no-cache \
        curl \
        git \
        make \
        g++ \
        cmake \
        jq \
        mosquitto-clients

ADD sources/ /opt/
ADD config/ /etc/inverter/

RUN cd /opt/inverter-cli && \
    mkdir bin && cmake . && make && mv inverter_poller bin/

WORKDIR /opt
CMD ["/opt/inverter-mqtt/entrypoint.sh"]
