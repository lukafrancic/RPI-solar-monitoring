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
    const extra = document.getElementById("mqtt-config");

    if (mode === "Standalone" || mode === "Simulator") {
        extra.classList.add("hidden");
    } else {
        extra.classList.remove("hidden");
    }
}


document.getElementById("RPI-select").addEventListener(
    "change", setConfigVisibility);


async function postData(url, data) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(data)
    });
  } catch (err) {
    alert("Error in POST ${url}:'", err);
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
    UCContainer = document.getElementById("user-config");
    populateConfigDiv("config-", config.user, UCContainer);

    MCContainer = document.getElementById("mqtt-config");
    populateConfigDiv("mqtt-", config.mqtt, MCContainer);
    
    UCContainer.querySelector("#RPI-select").value = config.user.mode;

    // document.getElementById("RPI-select").dispatchEvent(new Event("change"));
    setConfigVisibility();
}


async function sendConfig() {
    const payload = {
        user: {},
        mqtt: {}
    };

    UCContainer = document.getElementById("user-config");
    var divs = UCContainer.querySelectorAll(".form-row");
    divs.forEach((element) => {
        const divName = element.id.split("-");
        const input = element.querySelector("input");
        if (input && divName.length == 2) payload.user[divName[1]] = input.value;
    })
    payload.user["mode"] = UCContainer.querySelector("#RPI-select").value;
    
    MCContainer = document.getElementById("mqtt-config");
    var divs = MCContainer.querySelectorAll(".form-row");
    divs.forEach((element) => {
        const divName = element.id.split("-");
        const input = element.querySelector("input");
        if (input && divName.length == 2) payload.mqtt[divName[1]] = input.value;
    })

    await postData("/config", payload);
}


var ws = new WebSocket("ws://localhost:8000/ws");
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

loadConfig();
