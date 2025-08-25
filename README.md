# RPI-Solar-monitoring

Connect a Raspberry PI to a Solar Edge Inverter via Modbus TCP to control power usage on other devices.

The repository features three different use cases.

## Python Setup

Download the directory and run the following commands in a terminal:
```
python -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt
```

## Daemon setup

We want the PIs to run our script on each boot so we need to setup a daemon. 
Open a new terminal and run:
```
chmod +x /home/pi/RPI-solar-monitoring/start_script.sh
```

Now create a `systemmc` service:

```
sudo nano /etc/systemd/system/solar_startup.service
```
And put this inside:
```
[Unit]
Description=My Python Script Service
After=network.target

[Service]
ExecStart=/home/pi/RPI-solar-monitoring/start_script.sh
WorkingDirectory=/home/pi/RPI-solar-monitoring
StandardOutput=inherit
StandardError=inherit
Restart=always
RestartSec=20
User=pi

[Install]
WantedBy=multi-user.target
```

Now enable and start the service
```
sudo systemctl daemon-reload
sudo systemctl enable solar_startup.service
sudo systemctl start solar_startup.service
```

# Standalone PI

In this version you have on RPI connected to Modbus TCP and controlling the pins. Simply setup the config files and restart the PI.

# Two PIs

If the PIs will be connected to a different network, take a look at <a href="https://tailscale.com/">Tailscale</a> to make life a bit easier. Register for a free plan and install tailscale on bot PIs and register them. From there you receive a ipv4 adress to connect the two PIs together.

Run the publisher script in the Py that is connected to the inverter -> you also need a mqtt broker there. And run the subscriber script on your receiver PI.

## Mqqt setup

This part only applies if you need to send mesagges between two different PIs. For that we need a mqtt broker on the publisher PI. One common solution is to use Mosquitto mqqt. Follow this <a href="https://randomnerdtutorials.com/how-to-install-mosquitto-broker-on-raspberry-pi/">tutorial</a> for a better explanation:

Run the following commands:

```
sudo apt update

sudo apt upgrade

sudo apt install -y mosquitto mosquitto-clients

sudo systemctl enable mosquitto.service
```

Next we need to setup the mqtt credentials. Make sure these credentials match the credentials in `mqtt_config.json`.

```
sudo mosquitto_passwd -c /etc/mosuitto/passwd USERNAME
```

At this point you will be prompted to enter the password. Now we need to configure the config file.

```
sudo nano /etc/mosquitto/mosquitto.conf
```

Place this at the top of the file.
```
per_listener_settings True
```
And this at the bottom.
```
allow_anonymous false
listener 1883
password_file /etc/mosquitto/passwd
```
And now simply restart mqqt:
```
sudo systemctl restart mosquitto
```

# Git updates
To update the scripts from git use:
```
git pull origin main
```
