#!/bin/bash
# This is a start script template. This gets run after the PI boots.
# Create a copy of this file and rename to start_script
cd /home/pi/RPI-Solar-monitoring
source .venv/bin/activate

cd web
exec uvicorn main:app --host 0.0.0.0 --port 8000
