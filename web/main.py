import os
import sys
from pathlib import Path
import asyncio

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import lib


task = lib.TaskManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        print("loading config")
        config = lib.load_sys_config()
        print("starting task")
        
        async def start_background():
            await task.do_new_task(config.mode)

        asyncio.create_task(start_background())

        print("task started")
    except Exception as error:
        print(error)

    yield

    await task.cancel_task()



app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")



@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("static/index.html")



@app.get("/config")
async def get_config() -> lib.Config:
    sys = lib.load_sys_config()
    mqtt = lib.load_mqtt_config()
    modbus = lib.load_modbus_config()

    ret =  lib.Config(sys=sys, mqtt=mqtt, modbus=modbus)
    print(ret)
    return ret



@app.post("/config")
async def update_config(data: lib.Config) -> None:
    """
    Update config upon POST request.

    :param data: Data containing user and mqtt config. Only user config gets
    saved in case user.mode is Standalone.
    :type data: lib.Config
    """
    print("Updating configs")
    match data.sys.mode:
        case "Standalone":
            lib.update_config(data.sys)
            lib.update_config(data.modbus)
        case "Simulator":
            lib.update_config(data.sys)
        case "Subscriber":
            lib.update_config(data.sys)
            lib.update_config(data.mqtt)
        case "Publisher":
            lib.update_config(data.modbus)
            lib.update_config(data.mqtt)
        case _:
            print(f"Failed to update anything. Received: {data.sys.mode}")
            
    await task.cancel_task()
    await task.do_new_task(data.sys.mode)



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    task.add_socket(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            print(data)
            await task.manage_msg(data)
    except:
        task.remove_socket(websocket)
        print("Websocket failed")



@app.post("/shutdown")
async def shutdownDevice():
    try:
        os.system("sudo shutdown -h now")
    except Exception as err:
        print(f"Failed to shutdown device\n{err}")
        








