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
        config = lib.load_user_config()
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
    user = lib.load_user_config()
    mqtt = lib.load_mqtt_config()

    return lib.Config(user=user, mqtt=mqtt)



@app.post("/config")
async def update_config(data: lib.Config) -> None:
    """
    Update config upon POST request.

    :param data: Data containing user and mqtt config. Only user config gets
    saved in case user.mode is Standalone.
    :type data: lib.Config
    """
    lib.update_config(data.user)
    if data.user.mode != "Standalone":
        lib.update_config(data.mqtt)

    await task.cancel_task()
    await task.do_new_task(data.user.mode)



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print("insude websocket_endpoint")
    await websocket.accept()
    print("web socket accepted")
    task.add_socket(websocket)
    print("websocket added")
    try:
        while True:
            _ = await websocket.receive_text()
    except:
        task.remove_socket(websocket)









