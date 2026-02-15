import time
import threading
import logging
from pymodbus.client import AsyncModbusTcpClient
import asyncio
from typing import Union
import paho.mqtt.client as mqtt
from gpiozero import DigitalOutputDevice
from collections.abc import Callable

from lib.utils import *



class TimeBlock:

    TIME_ZONE = (
        (0, 6),
        (6, 7),
        (7, 14),
        (14, 16),
        (16, 20),
        (20, 22),
        (22, 24)
    )

    BLOCK = {
        1: (3, 2, 1, 2, 1, 2, 3), # Visja sezona delovni dan
        2: (4, 3, 2, 3, 2, 3, 4), # visja sezona dela prost dan
        3: (4, 3, 2, 3, 2, 3, 4), # nizja sezona delovni dan
        4: (5, 4, 3, 4, 3, 4, 5)  # nizja sezona dela prost dan
    }

    MONTHS = {
        1: ("H", (1, 2)), # novo leto
        2: ("H", (8,)), # presernov dan
        3: ("L", ()), 
        4: ("L", (27,)), # dan upora
        5: ("L", (1, 2)), # prvi maj
        6: ("L", (25,)), # dan drzavnosti
        7: ("L", ()),
        8: ("L", (15,)), # Marijino vnebozetje
        9: ("L", ()),
        10: ("L", (31,)), # dan reformacije
        11: ("H", (1,)), # dan spomina na mrtve
        12: ("H", (25, 26)) # bozic, dan samostojnosti
    }


    def __init__(self):
        self._prev_hour = -1
        self.ctime = time.time()
        self.ltime = time.localtime(self.ctime)


    def get_time_block(self) -> int:
        
        season, holiday = self.MONTHS[self.ltime.tm_mon]

        z_id = 0
        for i, zone in enumerate(self.TIME_ZONE):
            if zone[0] <= self.ltime.tm_hour and zone[1] > self.ltime.tm_hour:
                z_id = i
                break
        
        block_id = 0
        if self.ltime.tm_mday in holiday[1] or (
            self.ltime.tm_wday == 5 or self.ltime.tm_wday == 6):
            block_id = 1

        if season == "L":
            block_id += 2

        self._prev_hour = self.ltime.tm_hour

        return self.BLOCK[block_id[z_id]]


    def update_needed(self) -> bool:
        self.ctime = time.time()
        self.ltime = time.localtime(self.ctime)

        if self._prev_hour == self.ltime.tm_hour:
            return False
        
        return True
    


class DecisionMaker:
    """
    A class that runs the relay/alarm logic based on config settings and
    current power levels.
    """
    def __init__(self, config: SysConfig,
                 broadcaster: Callable[[TransferData], None] | None = None):
        """
        Params
            config: dictionary from load_json function
            acq_time: time step that will be used within the loop
        """
        self.config = config
        self._pow_high = self.config.limit_1
        self._pow_low = self.config.limit_1 - self.config.limit_diff
        self._pow_list = (
            self.config.limit_1, 
            self.config.limit_2, 
            self.config.limit_3, 
            self.config.limit_4, 
            self.config.limit_5
        )
        self.broadcaster = broadcaster
        self.current_time = time.monotonic()
        self.acq_time = config.cycle_time
        self.current_power = 0
        self.last_update = 0
        self._current_data = TransferData()

        self.data_logger = logging.getLogger("data_logger")
        self.tb = TimeBlock()

        # trackers
        self.current_state = State.STANDBY
        self._timer = 0

        self._lock = asyncio.Lock()
        self._is_updated = False
        self._event = asyncio.Event()

        self._initialize_pins()


    def _initialize_pins(self):
        self.relay_pins: list[DigitalOutputDevice] = []
        self._initialized = False
        self._pins = {}

        try:
            pins = self.config.relay_pins.split(";")
            for pin_name in pins:
                pin_name = pin_name.strip(" ")
                pin = DigitalOutputDevice(
                    pin_name, 
                    active_high=not self.config.invert_logic,
                    initial_value=False)
                self.relay_pins.append(pin)
                self._pins[pin_name] = pin

            self.alarm_pin = DigitalOutputDevice(
                self.config.alarm_pin, 
                active_high=not self.config.invert_logic,
                initial_value=False)
            self._pins[self.config.alarm_pin] = self.alarm_pin
            self._initialized = True

        except Exception as err:
            print(f"Failed to initialize pins:\n{err}")

    
    def _clear_pins(self):
        for (key, pin) in self._pins.items():
            try:
                pin.off()
                pin.close()
            except Exception as err:
                print(f"Failed to close pin {key}\n{err}")
        
        self._initialized = False
        

    def _set_relays(self, state: bool):
        """
        Relay handler.
        
        :param state: True calls pin.on() and False calls pin.off(). The
            output depends on config.invert_logic value.
        :type state: bool
        """
        if state:
            for pin in self.relay_pins:
                pin.on()
        else:
            for pin in self.relay_pins:
                pin.off()


    def _set_alarm(self, state: bool):
        """
        Alarm pin handler.
        
        :param state: True calls pin.on() and False calls pin.off(). The
            output depends on config.invert_logic value.
        :type state: bool
        """
        if state:
            self.alarm_pin.on()
        else:
            self.alarm_pin.off()


    def _decision_loop(self):
        """
        The main logic of the class. It acts upon the received power value.
        """
        self._timer += self.acq_time
       
        match self.current_state:
            case State.STANDBY:
                if self.current_power >= self._pow_high:
                    self.current_state = State.RELAY_ON
                
                self._timer = 0
                self._set_relays(False)
                self._set_alarm(False)

            case State.RELAY_ON:
                if self.current_power >= self._pow_high and (
                    self._timer > self.config.alarm_delay):
                    self.current_state = State.ALARM_ON
                    self._timer = 0

                if self.current_power < self._pow_low:
                    self.current_state = State.RELAY_TIMEOUT
                    self._timer = 0

                self._set_relays(True)
                self._set_alarm(False)

            case State.RELAY_TIMEOUT:
                if self.current_power >= self._pow_low:
                    self.current_state = State.RELAY_ON
                    self._timer = 0

                if self._timer >= self.config.relay_timeout:
                    self.current_state = State.STANDBY
                    self._timer = 0

                self._set_relays(True)
                self._set_alarm(False)

            case State.ALARM_ON:
                if self.current_power < self._pow_high:
                    self.current_state = State.RELAY_ON
                    self._timer = 0

                if self._timer >= self.config.alarm_on_time:
                    self.current_state = State.ALARM_TIMEOUT
                    self._timer = 0
                
                self._set_relays(True)
                self._set_alarm(True)

            case State.ALARM_TIMEOUT:
                if self.current_power < self._pow_high:
                    self.current_state = State.RELAY_ON
                    self._timer = 0

                if self._timer >= self.config.alarm_timeout:
                    self.current_state = State.ALARM_ON
                    self._timer = 0

                self._set_relays(True)
                self._set_alarm(False)

            case _:
                self._set_relays(False)
                self._set_alarm(False)
                self.current_state = State.STANDBY
                self._timer = 0
    

    def update_value(self, data: TransferData):
        # ideally this would have a lock, but it would require the
        # mqtt subcriber to be asynchronous as well
        self._current_data = data
        self.current_power = -data.grid
        self.last_update = time.monotonic()
        self.data_logger.info(f"Received {data}")
        self._is_updated = True


    async def loop(self):
        """
        Async loop that should be used by the Task Manager.
        """
        self._event.set()

        while self._event.is_set():
            t1 = time.monotonic()

            if self.tb.update_needed():
                block_id = self.tb.get_time_block()
                self._pow_high = self._pow_list[block_id-1]
                self._pow_low = self._pow_high - self.config.limit_diff

            async with self._lock:
                self._decision_loop()

                self._is_updated = False

                if t1 - self.last_update > self.config.connection_timeout:
                    self.current_power = 0

                if self.broadcaster:
                    self._current_data.status = self.current_state.name
                    await self.broadcaster(self._current_data)

                self.data_logger.info(f"State: {self.current_state}")

            t2 = time.monotonic()
            await asyncio.sleep(max(0.1, self.acq_time - t2 + t1))


    def stop(self):
        self._event.clear()
        self._clear_pins()



class SolarEdgeModbus:
    """
    Acquisition class to get data from inverter via Modbus.
    """
    PV_POWER = 83
    PV_SCALE = 84
    GRID_POWER = 206
    GRID_SCALE = 210


    def __init__(self, config: ModbusConfig, 
                 publisher: Union["MqqtPublisher", DecisionMaker],
                 broadcaster: Callable[[TransferData], None] = None):
        """
        config: dictionary from load_json function
        """
        self.client = AsyncModbusTcpClient(config.ip, port=config.port, 
                                      timeout = config.timeout)
        self.config = config
        self.acq_time = config.acq_time
        self.broadcaster = broadcaster
        self.grid_power = 0
        self.PV_power = 0
        self.current_load = 0

        self.error_logger = logging.getLogger("error_logger")
        self.data_logger = logging.getLogger("data_logger")

        self.publisher = publisher

        self._event = asyncio.Event()
        self._lock = asyncio.Lock()

        
    async def _read_register(self, address: int, count: int = 1) -> list[int]:
        """
        Tries to read registers in a safe way. If it fails an empty list is
        returned.

        :param address: modbus address to be read.
        """
        ret = None
        try:
            ret = await self.client.read_holding_registers(address, count=count)
        except:
            self.error_logger.exception("Read register error")

        if ret != None:
            return ret.registers
        
        return []


    async def get_new_data(self) -> None:
        """
        Run an infinite loop to acquire data via Modbus. Received power levels
        are in watts.
        """

        try:
            is_connected = await self.client.connect()
        except:
            self.error_logger.exception("Failed to connect")
            is_connected = False

        if is_connected:
            PV = await self._read_PV_power_value()
            GRID = await self._read_GRID_power_value()

            if PV is not None and GRID is not None:
                self.grid_power = GRID
                self.PV_power = PV
                # if we take from grid -> we get negative value
                # if we return to grid -> we get positive value
                self.current_load = PV - GRID
                
                # power levels are in watts
                self.data_logger.info(
                    f"{self.PV_power}\t{self.grid_power}\t{self.current_load}")
                
            else:
                self.grid_power = 0
                self.PV_power = 0
                self.current_load = 0
                self.error_logger.warning("No logged values")
            
            # self.error_logger.info(f"Load: {self.current_load} W")
        else:
            self.grid_power = 0
            self.PV_power = 0
            self.current_load = 0
            self.error_logger.warning("No modbus connection")

        # self.publisher.update_value(-self.grid_power)
        self.client.close()

        # return (self.PV_power, self.grid_power, self.current_load)
     
    
    async def _read_PV_power_value(self) -> int | None:
        """
        Read modbus values

        :param args: tuple of register to read -> value, scale

        :return int: if all is as expected 
        :return None: if error when reading
        """
        ret = await self._read_register(self.PV_POWER, 2)
        val, pval = 0, 0
        if len(ret) == 2:
            val = self._uint2int(ret[0])
            pval = self._uint2int(ret[1])
        else:
            self.error_logger.warning(f"No PV meter data. Received {len(ret)}")
            return
        
        if pval < 5 and pval > -5:
            return int(val * 10**pval)
        else:
            self.error_logger.warning(f"pval is too big: {pval} at "\
                                 f"{self.PV_POWER} -> {ret[0]}, {ret[1]}")
            return


    async def _read_GRID_power_value(self) -> int | None:
        """
        Read modbus values

        :param args: tuple of register to read -> value, scale

        :return int: if all is as expected 
        :return None: if error when reading
        """
        ret = await self._read_register(self.GRID_POWER, 5)
        val, pval = 0, 0
        if len(ret) == 5:
            val = self._uint2int(ret[0])
            pval = self._uint2int(ret[4])
        else:
            self.error_logger.warning(f"No GRID meter data. Received {len(ret)}")
            return
        
        if pval < 5 and pval > -5:
            return int(val * 10**pval)
        else:
            self.error_logger.warning(f"pval is too big: {pval} at " \
                                 f"{self.GRID_POWER} -> {ret[0]}, {ret[0]}")
            return


    def _uint2int(self, val) -> int:
        """
        Cast unsigned int to signed int.
        """
        if val >= 2**15:
            return val - 2**16
        
        return val


    async def loop(self) -> None:
        self._event.set()

        while self._event.is_set():
            t1 = time.monotonic()
            await self.get_new_data()

            self.publisher.update_value(TransferData(
                grid=self.grid_power, PV=self.PV_power, 
                load=self.current_load))
            
            if self.broadcaster:
                await self.broadcaster(TransferData(
                    grid=self.grid_power, PV=self.PV_power, 
                    load=self.current_load))

            t2 = time.monotonic()

            await asyncio.sleep(max(0.1, self.acq_time - t2 +t1))
    
    
    def stop(self):
        self._event.clear()



class MqqtSubscriber:
    def __init__(self, 
                 config: MqttConfig, 
                 decision_maker: DecisionMaker):
        self.config = config
        self.error_logger = logging.getLogger("error_logger")
        self.decision_maker = decision_maker

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        self.client.username_pw_set(username=self.config.username, 
                                    password=self.config.password)
        self.client.connect(self.config.broker_ip, self.config.port, 300)
        self.client.reconnect_delay_set(min_delay=10, max_delay=60)


    def on_connect(self, client, userdata, flags, rc):
        client.subscribe(self.config.topic)
        time.sleep(0.5)
        self.error_logger.info(f"Connected with result code {str(rc)}")


    def on_message(self, client, userdata, msg):
        self.latest_msg = msg.payload.decode()
        self.error_logger.info(f"Received: {self.latest_msg}")
        try:
            val = json.loads(self.latest_msg)
            data = TransferData(**val)
            self.decision_maker.update_value(data)
            
        except:
            self.error_logger.error("Unable to cast msg to int!")


    def on_disconnect(self, client, userdate, rc):
        self.error_logger.info(f"Disconnected with result code {str(rc)}")


    def start_loop(self):
        self.client.loop_start()

    
    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()





class MqqtPublisher:
    def __init__(self, config: MqttConfig):
        self.config = config
        self.error_logger = logging.getLogger("error_logger")

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

        self.client.username_pw_set(username=self.config.username, 
                                    password=self.config.password)
        self.client.connect(self.config.broker_ip, self.config.port, 300)
        self.client.reconnect_delay_set(min_delay=10, max_delay=60)


    def on_connect(self, client, userdata, flags, rc):
        client.subscribe(self.config.topic)
        self.error_logger.info(f"Connected with result code {str(rc)}")


    def on_disconnect(self, client, userdata, rc):
        self.error_logger.info(f"Disconnected with result code {str(rc)}")


    def update_value(self, data: TransferData):
        msg = data.model_dump_json()
        ret = self.client.publish(
            self.config.topic, payload=msg, qos=2, retain=False
        )
        if ret.rc == mqtt.MQTT_ERR_SUCCESS:
            self.error_logger.info(f"Publisher sent: {msg}")
        else:
            self.error_logger.warning(f"Publisher failed: {ret.rc}")


    def start_loop(self):
        self.client.loop_start()

    
    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

