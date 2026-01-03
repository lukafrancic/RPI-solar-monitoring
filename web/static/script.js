let currentMode;
let isManual = false;
var ws = new WebSocket(
  (location.protocol === "https:" ? "wss://" : "ws://") +
  location.host +
  "/ws"
);

ws.onopen = () => console.log("WebSocket connected");
ws.onmessage = e => console.log("Message:", e.data);
ws.onerror = e => console.error("WebSocket error", e);
ws.onclose = () => console.log("WebSocket closed");


function toggleMenu() {
    const menu = document.getElementById("side-menu");
    menu.classList.toggle("open");
}


function menuAction(name) {
    console.log("Clicked:", name);
    // alert("Clicked: " + name);
    document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
    document.getElementById("screen-" + name).classList.remove('hidden');
}

function setConfigVisibility(){
    const mode = document.getElementById("RPI-select").value;
    const sys_config = document.getElementById("sys-config");
    const modbus_config = document.getElementById("modbus-config");
    const mqtt_config = document.getElementById("mqtt-config");
    const manual = document.getElementById("manual-control");

    switch (mode) {
        case "Simulator":
            sys_config.classList.remove("hidden");
            modbus_config.classList.add("hidden");
            mqtt_config.classList.add("hidden");
            if (isManual) {
                manual.classList.remove("hidden");
            }
            break;
        
        case "Standalone":
            sys_config.classList.remove("hidden");
            modbus_config.classList.remove("hidden");
            mqtt_config.classList.add("hidden");
            manual.classList.add("hidden");
            break;
        case "Subscriber":
            sys_config.classList.remove("hidden");
            modbus_config.classList.add("hidden");
            mqtt_config.classList.remove("hidden");
            manual.classList.add("hidden");
            break;
        case "Publisher":
            sys_config.classList.add("hidden");
            modbus_config.classList.remove("hidden");
            mqtt_config.classList.remove("hidden");
            manual.classList.add("hidden");
            break;
        default:
            console.log("Failed at setting config visibility");
    }


}


document.getElementById("RPI-select").addEventListener(
    "change", setConfigVisibility);


async function postData(url, data) {
  try {
    if (data) {
        const res = await fetch(url, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data)
        });
    } else {
        const res = await fetch(url, {
            method: "POST"
        });
    }
  } catch (err) {
    alert(`Error in POST ${url}: ${err}`);
  }
}


async function getConfig() {
    try {
        // console.log("Fetching config");
        const ret = await fetch("/config");

        if (!ret.ok) {
            throw new Error(`Load config error: ${ret.status}`);
        }

        const result = await ret.json();
        // console.log(result);
        return result;
    } catch (error) {
        console.error(error.message);
        return;
    }
}


function populateConfigDiv(prefix, data, container) {
    console.log("populateConfig");
    console.log(data);
    try{
        for (const [key, value] of Object.entries(data)) {
            const div = container.querySelector(`#${prefix}${key}`);
            console.log(div);
            if (!div) continue;

            const input = div.querySelector("input");
            if (!input) continue;

            input.value = value;
        }
    } catch (error) {
        console.error(error.message);
    }
}


async function loadConfig() {
    const config = await getConfig();
    if (!config) return;

    // console.log(config);
    const sysContainer = document.getElementById("sys-config");
    populateConfigDiv("config-", config.sys, sysContainer);

    const ModbusContainer = document.getElementById("modbus-config");
    populateConfigDiv("modbus-", config.modbus, ModbusContainer);

    const MqttContainer = document.getElementById("mqtt-config");
    populateConfigDiv("mqtt-", config.mqtt, MqttContainer);
    
    const RPISelect = document.getElementById("RPI-select");
    RPISelect.value = config.sys.mode;

    // document.getElementById("RPI-select").dispatchEvent(new Event("change"));
    loadManual(config.sys);

    currentMode = config.sys.mode;
    isManual = (currentMode == "Simulator");
    setConfigVisibility();
}


function loadManual(config) {
    const container = document.getElementById("manual-control");

    const data = {}
    data[config.alarm_pin] = "Alarm pin";
    const relays = config.relay_pins.split(";")
    relays.forEach((element) => {
        data[element] = "Relay pin";
    })

    for (const [key, value] of Object.entries(data)) {
        const new_div = document.createElement("div");
        new_div.className = "form-row hoverBox";
        new_div.innerHTML = `
            <label for="manual-label-${key}">${key}</label>
            <label class="switch">
                <input id="manual-label-${key}" 
                    type="checkbox" 
                    class="switch-input"
                    data-pin="${key}">
                <span class="slider round"></span>
            </label>
            <div class="tooltip">${value}</div>
        `;
        container.appendChild(new_div);
    }
}



async function sendConfig() {
    const payload = {
        sys: {},
        modbus: {},
        mqtt: {}
    };

    const sysContainer = document.getElementById("sys-config");
    var divs = sysContainer.querySelectorAll(".form-row");
    divs.forEach((element) => {
        get_input_value(element, payload.sys);
    })

    payload.sys["mode"] = document.getElementById("RPI-select").value;
    
    const mqttContainer = document.getElementById("mqtt-config");
    var divs = mqttContainer.querySelectorAll(".form-row");
    divs.forEach((element) => {
        get_input_value(element, payload.mqtt);
    })

    const modbusContainer = document.getElementById("modbus-config");
    var divs = modbusContainer.querySelectorAll(".form-row");
    divs.forEach((element) => {
        get_input_value(element, payload.modbus);
    })

    await postData("/config", payload);

    const container = document.getElementById("manual-control");
    container.innerHTML = "";
    while (container.firstChild) {
        container.removeChild.firstChild;
    }
    loadManual(payload.sys);
}


function get_input_value(element, data) {
    const divName = element.id.split("-");
    const input = element.querySelector("input");
    if (!input || divName.length !== 2) return;

    let value;
    
    switch (input.type) {
        case "checkbox":
            value = input.checked;
            break;
        case "number":
            value = input.value === "" ? null : Number(input.value);
            break;
        default:
            value = input.value;
    }
    data[divName[1]] = value;
}


ws.onmessage = function(event) {
    const data = JSON.parse(event.data);

    const container = document.getElementById("screen-dashboard");
    container.querySelector("#house-label").textContent = data.load;
    container.querySelector("#panel-label").textContent = data.PV;
    container.querySelector("#grid-label").textContent = data.grid;
    container.querySelector("#junction-label").textContent = data.status;

    // console.log(`${event.data}`);
    // console.log(`${data}`);
};



document.getElementById("manual-control").addEventListener("change", (event) => {
    if (!event.target.matches(".switch-input")) return;

    const checkbox = event.target;

    const payload = {
        pin: checkbox.dataset.pin,
        enabled: checkbox.checked
    };

    ws.send(JSON.stringify(payload));
    console.log(payload);
});


async function shutdownDevice(){
    await postData("/shutdown", null);
}


loadConfig();
