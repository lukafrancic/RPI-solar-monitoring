import time
import threading
import logging
from pymodbus.client import AsyncModbusTcpClient
import asyncio
from typing import Union
import paho.mqtt.client as mqtt
from gpiozero import DigitalOutputDevice

from .utils import *



class DecisionMaker:
    """
    A class that runs the relay/alarm logic based on config settings and
    current power levels.
    """
    def __init__(self, config: UserConfig, acq_time: int = 30):
        """
        Params
            config: dictionary from load_json function
            acq_time: time step that will be used within the loop
        """
        self.config = config
        self.current_time = time.monotonic()
        self.acq_time = acq_time
        self.current_power = 0
        self.last_update = 0

        self.data_logger = logging.getLogger("data_logger")

        # trackers
        self.current_state = State.STANDBY
        self.is_relay = False
        self.relay_on_time = 0
        self.relay_timeout_time = 0
        self.is_alarm = False
        self.alarm_on_time = 0
        self.alarm_timeout_time = 0

        self._thread_status = False
        self._lock = threading.Lock()
        self._thread = None
        self._is_updated = False

        self._initialize_pins()


    def _initialize_pins(self):
        self.relay_pins = []
        for pin_name in self.config["relay_pins"]:
            pin = DigitalOutputDevice(pin_name)
            self.relay_pins.append(pin)

        self.alarm_pin = DigitalOutputDevice(self.config["alarm_pin"])
        

    def _set_relays(self, state: bool):
        """
        The pin logic is inverted. To turn something on, pull the pin LOW.
        The relays will be mostly set to off to prevent unnecessary heating.

        :param state: turn on or off
        """
        if state:
            for pin in self.relay_pins:
                pin.off()
        else:
            for pin in self.relay_pins:
                pin.on()


    def _set_alarm(self, state: bool):
        """
        The pin logic is inverted. To turn something on, pull the pin LOW.
        The relays will be mostly set to off to prevent unnecessary heating.

        :param state: turn on or off
        """
        if state:
            self.alarm_pin.off()
        else:
            self.alarm_pin.on()


    def _decision_loop(self):
        """
        The main logic of the class. It acts upon the received power value.
        """

        if self.current_power < self.config["limit"] and not self.is_relay:
            self.current_state = State.STANDBY

        if self.current_power >= self.config["limit"]:
            self.current_state = State.RELAY_ON

        if (self.current_power < self.config["lower_pow_limit"]
             and self.is_relay):
            self.current_state = State.RELAY_TIMEOUT

        if (self.current_power  >= self.config["limit"] and self.is_relay
             and self.relay_on_time >= self.config["alarm_delay"]): 
            self.current_state = State.ALARM_ON

        if (self.current_power >= self.config["limit"] and self.is_relay
             and self.is_alarm 
             and self.alarm_on_time >= self.config["alarm_on_time"]):
            self.current_state = State.ALARM_TIMEOUT
       
        match self.current_state:
            case State.STANDBY:
                self.relay_timeout_time = 0
                self.relay_on_time = 0
                self.alarm_on_time = 0
                self.is_relay = False
                self.is_alarm = False
                
                # all relays off (pins go to HIGH)
                self._set_relays(False)
                self._set_alarm(False)

            case State.RELAY_ON:
                self.relay_on_time += self.acq_time
                self.alarm_on_time = 0
                self.relay_timeout_time = 0
                self.is_relay = True
                self.is_alarm = False
                # turn on relay
                self._set_relays(True)
                # turn on alarm
                self._set_alarm(False)

            case State.RELAY_TIMEOUT:
                self.relay_timeout_time += self.acq_time
                self.relay_on_time += self.acq_time
                self.alarm_on_time = 0
                self.is_relay = True
                self.is_alarm = False
                # to bi moralo avtomatsko preiti v STANDBY
                if self.relay_timeout_time > self.config["relay_timeout"]:
                    self.is_relay = False
                # turn on relay
                self._set_relays(True)
                # turn off alarm
                self._set_alarm(False)

            case State.ALARM_ON:
                self.relay_on_time += self.acq_time
                self.alarm_on_time += self.acq_time
                self.relay_timeout_time = 0
                self.is_relay = True
                self.is_alarm = True
                # turn on relay
                self._set_relays(True)
                # turn on alarm
                self._set_alarm(True)

            case State.ALARM_TIMEOUT:
                self.relay_on_time += self.acq_time
                self.alarm_on_time += self.acq_time
                self.relay_timeout_time = 0
                self.is_relay = True
                self.is_alarm = True
                # to bi moralo preiti nazaj v ALARM_ON
                if self.alarm_on_time >= self.config["alarm_timeout"]:
                    self.alarm_on_time = 0
                # turn on relay
                self._set_relays(True)
                # turn off alarm
                self._set_alarm(False)
            case _:
                pass
    

    def update_value(self, power_load: int):
        with self._lock:
            self.current_power = power_load
            self.last_update = time.monotonic()
            self.data_logger.info(f"Received {power_load}")
            self._is_updated = True


    def _loop(self):
        while True:
            t1 = time.monotonic()
            
            with self._lock:
                self._decision_loop()

                if self._is_updated:
                    self._is_updated = False

                if t1 - self.last_update > self.config["connection_timeout"]:
                    self.current_power = 0

                self.data_logger.info(f"State: {self.current_state}")

            time.sleep(self.acq_time)


    def start_loop(self):
        if not self._thread_status:
            self._thread = threading.Thread(target=self._loop)
            self._thread.start()
            self._thread_status = True

    
    def stop_loop(self):
        if self._thread_status:
            self._thread.join()
            self._thread_status = False



class ModbusAcq:
    """
    Acquisition class to get data from inverter via Modbus.
    """
    PV_POWER = 83
    PV_SCALE = 84
    GRID_POWER = 206
    GRID_SCALE = 210


    def __init__(self, config: UserConfig, 
                 publisher: Union["MqqtPublisher", DecisionMaker], 
                 acq_time: int = 30):
        """
        config: dictionary from load_json function
        """
        self.client = AsyncModbusTcpClient(config["ip"], port=config["port"], 
                                      timeout = 0.1)
        self.grid_power = 0
        self.PV_power = 0
        self.current_load = 0

        self.error_logger = logging.getLogger("error_logger")
        self.data_logger = logging.getLogger("data_logger")

        self.publisher = publisher
        self.acq_time = acq_time

        
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
            # locena funkcija za branje, nvm kako to bolj pametno naredit...
            # moramo brati skupaj, ker drugace na neki tocki zamenja vrstni
            # red branja registrov
            PV = await self._read_PV_power_value()
            # await asyncio.sleep(1)
            GRID = await self._read_GRID_power_value()

            if PV is not None and GRID is not None:
                self.grid_power = GRID
                self.PV_power = PV
                if GRID >= 0:
                    self.current_load = PV - GRID
                else:
                    self.current_load = PV + GRID
                
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

        self.publisher.update_value(-self.grid_power)
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
        while True:
            t1 = time.monotonic()

            await self.get_new_data()

            t2 = time.monotonic()

            await asyncio.sleep((self.acq_time - t2 +t1))
    


class MqqtSubscriber:
    def __init__(self, config: MqqtConfig, decision_maker: DecisionMaker):
        self.config = config
        self.error_logger = logging.getLogger("error_logger")
        self.decision_maker = decision_maker

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        self.client.username_pw_set(username=self.config["username"], 
                                    password=self.config["password"])
        self.client.connect(self.config["broker_ip"], self.config["port"], 300)


    def on_connect(self, client, userdata, flags, rc):
        client.subscribe(self.config["topic"])
        time.sleep(0.5)
        self.error_logger.info(f"Connected with result code {str(rc)}")


    def on_message(self, client, userdata, msg):
        self.latest_msg = msg.payload.decode()
        self.error_logger.info(f"Received: {self.latest_msg}")
        try:
            power = int(self.latest_msg)
            self.decision_maker.update_value(power)
            
        except:
            self.error_logger.error("Unable to cast msg to int!")


    def on_disconnect(self, client, userdate, rc):
        self.error_logger.info(f"Disconnected with result code {str(rc)}")


    def loop(self):
        self.client.loop_forever(retry_first_connection=True)



class MqqtPublisher:
    def __init__(self, config: MqqtConfig):
        self.config = config
        self.error_logger = logging.getLogger("error_logger")

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

        self.client.username_pw_set(username=self.config["username"], 
                                    password=self.config["password"])
        self.client.connect(self.config["broker_ip"], self.config["port"], 300)


    def on_connect(self, client, userdata, flags, rc):
        client.subscribe(self.config["topic"])
        self.error_logger.info(f"Connected with result code {str(rc)}")


    def on_disconnect(self, client, userdata, rc):
        self.error_logger.info(f"Disconnected with result code {str(rc)}")


    def update_value(self, msg: str, qos: int=2, retain: bool=False):
        ret = self.client.publish(
            self.config["topic"], payload=msg, qos=qos, retain=retain
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


