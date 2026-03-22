#!/bin/bash
set -e

if [ ! -f /home/container/main.py ]; then
    cp -r /opt/bot/. /home/container/
fi

mkdir -p /home/container/data /home/container/assets

cd /home/container
exec bash -c "${STARTUP:-python3 main.py}"
