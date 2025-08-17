from enum import Enum, auto
from typing import TypedDict
import json
from pathlib import Path
import logging
import logging.config


CONFIG_DIR = Path(__file__).resolve().parent / "config"

class UserConfig(TypedDict):
    ip : str # inverter IP
    port : int # inverter Port num
    limit : int # alarm goes up when this limit is passed
    alarm_on_time : int # alarm stays on for N seconds
    alarm_timeout : int # alarm starts again after N seconds
    alarm_delay : int    # turn on the alarm is power is still too high N seconds after relay on time
    lower_pow_limit : int # relay switches back when the power goes lower
    relay_timeout : int  # relays switch after N seconds after going bellow lower lim    
    connection_timeout: int # After N seconds the load value resets to 0 in DecisionMaker



class MqqtConfig(TypedDict):
    ip: str # broker ip
    username: str
    password: str
    port: int
    topic: str



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
    Load config stored as json object.

    returns a dict.
    """
    # filename = pathlib.Path(".config/user_config.json")
    filename = CONFIG_DIR / "user_config.json"

    return load_json(filename)



def load_mqtt_config() -> MqqtConfig:
    """
    Load config stored as json object.

    returns a dict.
    """
    # filename = pathlib.Path(".config/mqtt_config.json")
    filename = CONFIG_DIR / "mqtt_config.json"
    
    return load_json(filename)



def setup_logging(LOG_DIR):
    # config_file = pathlib.Path("/config/logging_config.json")
    # config_file = "/config/logging_config.json"
    config_file = CONFIG_DIR / "logging_config.json"
    with open(config_file) as file:
        config = json.load(file)
        
    config['handlers']['file_err']['filename'] = str(LOG_DIR / 'error.log')
    config['handlers']['file_data']['filename'] = str(LOG_DIR / 'data.log')

    logging.config.dictConfig(config)