#!/bin/bash
cd /home/elhassan/agent-service

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

# Start the server
~/.local/bin/uvicorn main:app --host 0.0.0.0 --port 8000
