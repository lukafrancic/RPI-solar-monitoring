import asyncio
from pathlib import Path

from lib import *


async def main():
    # wait a bit before startup
    asyncio.sleep(10)
    LOG_DIR = Path(__file__).resolve().parent / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    setup_logging(LOG_DIR)

    user_config = load_user_config()
    publisher = DecisionMaker(user_config)
    publisher.start_loop()

    user_config = load_user_config()
    data_acq = ModbusAcq(user_config, publisher)

    await asyncio.gather(data_acq.loop())


if __name__ == "__main__":
    asyncio.run(main())