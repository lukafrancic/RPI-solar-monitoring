from pathlib import Path
import asyncio
import random
from fastapi import WebSocket
from collections.abc import Callable

from lib.core import DecisionMaker, SolarEdgeModbus, MqqtPublisher, MqqtSubscriber
from lib.utils import *


class BaseMode:
    def __init__(self, broadcaster: Callable[[TransferData], None]):
        self.brodcaster = broadcaster
        self.publisher: DecisionMaker | MqqtPublisher = None
        self.data_acq: SolarEdgeModbus | MqqtSubscriber = None
        log_dir = Path(__file__).resolve().parents[1] / "logs"
        log_dir.mkdir(exist_ok=True)
        setup_logging(log_dir)


    def get_task(self):
        """
        Return a Coroutine or None
        """
        raise NotImplementedError


    def stop_task(self):
        if self.publisher:
            self.publisher.stop()
        if self.data_acq:
            self.data_acq.stop()



class Simulator(BaseMode):
    def __init__(self, broadcaster: Callable[[TransferData], None]):
        super().__init__(broadcaster)
        self._event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._loop_time = 5
        self._data: TransferData = TransferData(
            grid=0,PV=0,load=0,status="NA")
        self._is_updated = False


    async def loop(self):
        while self._event.is_set():
            async with self._lock:
                self._data.grid = random.randint(0, 100)
                self._data.PV = random.randint(0, 100)
                self._data.load = self._data.grid + self._data.PV
                self._is_updated = True

            print("broadcasted data")
            if self.brodcaster is not None:
                await self.brodcaster(self._data)

            await asyncio.sleep(self._loop_time)


    def get_task(self):
        print("got task request")
        user_config = load_user_config()
        # self._loop_time = user_config.inverter_cycle_time
        self._event.set()

        return self.loop()


    def stop_task(self):
        self._event.clear()



class Standalone(BaseMode):
    def get_task(self):
        user_config = load_user_config()
        self.publisher = DecisionMaker(user_config, 5)
        self.publisher.start_loop()

        user_config = load_user_config()
        self.data_acq = SolarEdgeModbus(
            user_config, self.publisher, self.brodcaster)

        return self.data_acq.loop()



class Publisher(BaseMode):
    def get_task(self):
        mqtt_config = load_mqtt_config()
        self.publisher = MqqtPublisher(mqtt_config)
        self.publisher.start_loop()
        
        user_config = load_user_config()
        self.data_acq = SolarEdgeModbus(
            user_config, self.publisher, self.brodcaster)

        return self.data_acq.loop()



class Subscriber(BaseMode):
    def get_task(self):
        user_config = load_user_config()
        self.publisher = DecisionMaker(user_config, 5)
        self.publisher.start_loop()

        mqtt_config = load_mqtt_config()
        self.data_acq = MqqtSubscriber(
            mqtt_config, self.publisher, self.brodcaster)
        
        return None
    


class TaskManager:
    def __init__(self):
        self.model: BaseMode = None
        self.task: asyncio.Task = None
        self.sockets: set[WebSocket] = set()


    def add_socket(self, socket: WebSocket):
        self.sockets.add(socket)


    def remove_socket(self, socket: WebSocket):
        self.sockets.discard(socket)


    async def do_new_task(self, name: str):
        if self.task:
            await self.cancel_task()
        await asyncio.sleep(1)

        match name:
            case "Standalone":
                self.model = Standalone(self.broadcast)
            case "Publisher":
                self.model = Publisher(self.broadcast)
            case "Subscriber":
                self.model = Subscriber(self.broadcast)
            case "Simulator":
                self.model = Simulator(self.broadcast)
            case _:
                self.model = None
        
        if self.model is not None:
            task = self.model.get_task()
            if task is not None:
                self.task = asyncio.create_task(task)

        print("new task started")
        

    async def cancel_task(self):
        if self.model is not None:
            self.model.stop_task()

        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

        self.model = None
        self.task = None


    async def broadcast(self, msg: TransferData):
        dead = []
        print("broadcasting in task manager")
        for ws in self.sockets:
            try:
                await ws.send_json(msg.model_dump())
            except:
                dead.append(ws)

        for ws in dead:
            self.sockets.discard(ws)
        