from ..lib import *



if __name__ == "__main__":
    setup_logging()

    user_config = load_user_config()
    dec_maker = DecisionMaker(user_config)
    dec_maker.start_loop()

    mqtt_config = load_mqtt_config()
    subscriber = MqqtSubscriber(mqtt_config, dec_maker)
    subscriber.loop()