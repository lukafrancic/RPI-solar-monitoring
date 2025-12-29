from pathlib import Path
import asyncio
import random
from fastapi import WebSocket
from collections.abc import Callable
from gpiozero import DigitalOutputDevice

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


    def get_task(self) -> list:
        """
        Return a Coroutine or None
        """
        raise NotImplementedError


    def stop_task(self):
        if self.publisher:
            self.publisher.stop()
        if self.data_acq:
            self.data_acq.stop()


    async def manage_msg(self, msg: str):
        print(msg)



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
        self._config = load_sys_config()
        self._event.set()
        self._pins = {}
        self._initialized = False
        
        try:
            pins = self._config.relay_pins.split(";")
            for pin in pins:
                pin = pin.strip(" ")
                self._pins[pin] = DigitalOutputDevice(pin)
            
            alarm_pin = self._config.alarm_pin
            self._pins[alarm_pin] = DigitalOutputDevice(alarm_pin)

            self._initialized = True

        except Exception as err:
            print(f"Failed to initialize pins {err}")

        return [self.loop()]


    def stop_task(self):
        self._event.clear()

        for (key, pin) in self._pins.items():
            try:
                pin.off()
                pin.close()
            except Exception as err:
                print(f"Failed to close pin {key}\n{err}")
        
        self._initialized = False


    async def manage_msg(self, msg):
        print("Managing msg")
        if not self._initialized:
            return
        try:
            msg = json.loads(msg)
            if msg["enabled"]:
                self._pins[msg["pin"]].on()
            else:
                self._pins[msg["pin"]].off()
        except Exception as err:
            print(f"Error while managing msg:\n{err}")



class Standalone(BaseMode):
    def get_task(self):
        sys_config = load_sys_config()
        self.publisher = DecisionMaker(sys_config, self.brodcaster)

        modbus_config = load_modbus_config()
        self.data_acq = SolarEdgeModbus(modbus_config, self.publisher)

        return [self.data_acq.loop(), self.publisher.loop()]



class Publisher(BaseMode):
    def get_task(self):
        mqtt_config = load_mqtt_config()
        self.publisher = MqqtPublisher(mqtt_config)
        self.publisher.start_loop()
        
        modbus_config = load_modbus_config()
        self.data_acq = SolarEdgeModbus(
            modbus_config, self.publisher, self.brodcaster)

        return [self.data_acq.loop()]



class Subscriber(BaseMode):
    def get_task(self):
        sys_config = load_sys_config()
        self.publisher = DecisionMaker(sys_config, self.brodcaster)

        mqtt_config = load_mqtt_config()
        self.data_acq = MqqtSubscriber(mqtt_config, self.publisher)
        self.data_acq.start_loop()

        return [self.publisher.loop()]
    


class TaskManager:
    def __init__(self):
        self.model: BaseMode = None
        self.task_list: list[asyncio.Task] = None
        self.sockets: set[WebSocket] = set()


    def add_socket(self, socket: WebSocket):
        self.sockets.add(socket)


    def remove_socket(self, socket: WebSocket):
        self.sockets.discard(socket)


    async def do_new_task(self, name: str):
        if self.task_list:
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
            task_list = self.model.get_task()
            if task_list is not None:
                for task in task_list:
                    self.task_list.append(asyncio.create_task(task))

        print("new task started")


    async def cancel_task(self):
        if self.model is not None:
            self.model.stop_task()

        if self.task_list is not None:
            for task in self.task_list:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        self.model = None
        self.task_list = []


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


    async def manage_msg(self, msg: str):
        if self.model:
            await self.model.manage_msg(msg)
        