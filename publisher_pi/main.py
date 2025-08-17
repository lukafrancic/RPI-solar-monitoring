import asyncio

from ..lib import *


async def main():
    setup_logging()

    mqtt_config = load_mqtt_config()
    publisher = MqqtPublisher(mqtt_config)

    user_config = load_user_config()
    data_acq = ModbusAcq(user_config, publisher)

    await asyncio.gather(data_acq.loop)


if __name__ == "__main__":
    asyncio.run(main())