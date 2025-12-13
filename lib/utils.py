from enum import Enum, auto
from pydantic import BaseModel
import json
from pathlib import Path
import os
import logging
import logging.config


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"



class UserConfig(BaseModel):
    mode: str = "Simulator" # RPI-setup
    ip : str = "192.168.1.45" # inverter IP
    port : int = 1502 # inverter Port num
    limit : int = 5000 # alarm goes up when this limit is passed
    alarm_on_time : int = 15 # alarm stays on for N seconds
    alarm_timeout : int = 60 # alarm starts again after N seconds
    alarm_delay : int = 40   # turn on the alarm is power is still too high N seconds after relay on time
    lower_pow_limit : int = 4000 # relay switches back when the power goes lower
    relay_timeout : int = 300 # relays switch after N seconds after going bellow lower lim    
    connection_timeout: int = 300 # After N seconds the load value resets to 0 in DecisionMaker
    alarm_pin: str = "J8:3"
    relay_pins: str = "J8:11; J8:13" # list of pins GPIO pins to use, separated by ;
    inverter_cycle_time: int = 30
    logic_cycle_time: int = 5



class MqttConfig(BaseModel):
    broker_ip: str = "192.168.1.54" # broker ip
    username: str = "username"
    password: str = "password"
    port: int = 1883
    topic: str = "Power"



class Config(BaseModel):
    user: UserConfig
    mqtt: MqttConfig



class TransferData(BaseModel):
    grid: int
    PV: int
    load: int
    status: str



class State(Enum):
    STANDBY = auto()
    RELAY_ON = auto()
    RELAY_TIMEOUT = auto()
    ALARM_ON = auto()
    ALARM_TIMEOUT = auto()



def load_json(filename: str) -> dict:
    """
    Load config stored as json object.

    returns a dict.
    """

    with open(filename, "r") as file:
        data = json.load(file)

    return data



def load_user_config() -> UserConfig:
    """
    Load config stored as an UserConfig object.
    If file doesn't exist or fails to load, it returns an UserConfig instance
    with default parameters.
    """
    filename = CONFIG_DIR / "user_config.json"
    if os.path.exists(filename):
        try:
            config = load_json(filename)
            return UserConfig(**config)
        except Exception as error:
            print(f"Failed to load json file:\n{error}\nUsing default values.")
    
    return UserConfig()



def load_mqtt_config() -> MqttConfig:
    """
    Load config stored as an MqttConfig object.
    If file doesn't exist or fails to load, it returns an UserConfig instance
    with default parameters.
    """
    filename = CONFIG_DIR / "mqtt_config.json"
    if os.path.exists(filename):
        try:
            config = load_json(filename)
            return MqttConfig(**config)
        except Exception as error:
            print(f"Failed to load json file:\n{error}\nUsing default values.")
    
    return MqttConfig()



def update_config(data: MqttConfig | UserConfig) -> None:
    """
    Save the updated config file.
    
    :param data: Input data to save as json file.
    :type data: MqqtConfig | UserConfig
    """

    if isinstance(data, UserConfig):
        filename = CONFIG_DIR / "user_config.json"
    elif isinstance(data, MqttConfig):
        filename = CONFIG_DIR / "mqtt_config.json"
    else:
        raise TypeError(f"Received unxpected type of {type(data)}!")
    
    data_json = data.model_dump_json(ensure_ascii=False, indent=4)

    with open(filename, "w") as file:
        file.write(data_json)



def setup_logging(LOG_DIR):
    # config_file = pathlib.Path("/config/logging_config.json")
    # config_file = "/config/logging_config.json"
    config_file = CONFIG_DIR / "logging_config.json"
    with open(config_file) as file:
        config = json.load(file)
        
    config['handlers']['file_err']['filename'] = str(LOG_DIR / 'error.log')
    config['handlers']['file_data']['filename'] = str(LOG_DIR / 'data.log')

    logging.config.dictConfig(config)