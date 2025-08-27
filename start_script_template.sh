#!/bin/bash
cd /home/pi/RPI-Solar-monitoring
source .venv/bin/activate

# Make sure to select the proper folder
# Create a copy of this file and rename to start_script
# exec python -m publisher_pi.main

# exec python -m subscriber_pi.main

exec python -m standalone_pi.main
