#!/bin/bash
cd /home/pi/your_project
source .venv/bin/activate

# Make sure to select the proper folder
# Create a copy of this file and rename to start_script
# exec python publisher_pi.main

# exec python sbuscriber_pi.main

exec python standalone_pi.main
