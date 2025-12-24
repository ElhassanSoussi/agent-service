#!/bin/bash
# Keepalive script - ensures server stays running

cd /home/elhassan/agent-service

while true; do
    # Check if server is running
    if ! curl -s --max-time 2 http://localhost:8000/health > /dev/null 2>&1; then
        echo "[$(date)] Server down, restarting..."

        # Kill any stuck processes
        pkill -9 -f "uvicorn main:app"
        sleep 2

        # Start server
        ~/.local/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/agent-service.log 2>&1 &

        sleep 5
        echo "[$(date)] Server restarted"
    fi

    # Check every 30 seconds
    sleep 30
done
