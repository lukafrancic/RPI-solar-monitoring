from pathlib import Path
import time
from lib import *



if __name__ == "__main__":
    # wait a bit before startup
    time.sleep(10)
    LOG_DIR = Path(__file__).resolve().parent / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    setup_logging(LOG_DIR)

    user_config = load_user_config()
    dec_maker = DecisionMaker(user_config, 5)
    dec_maker.start_loop()

    print("starting mqtt")
    mqtt_config = load_mqtt_config()
    subscriber = MqqtSubscriber(mqtt_config, dec_maker)
    print("subscriber initialized")
    subscriber.loop()