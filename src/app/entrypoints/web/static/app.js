// UI glue, no framework. Two kinds of button:
//   data-run="/api/..."   -> quick JSON call (health, import-status)
//   data-stream="command" -> long command; streams live output, Stop terminates it

const output = document.getElementById("output");
const healthList = document.getElementById("health-list");
const stopBtn = document.getElementById("stop-btn");

function env() {
  return document.getElementById("env").value;
}

// Form body for a command (data-form tells us which extra fields to include).
function bodyFor(form, command) {
  const data = new FormData();
  data.append("env", env());
  if (command) data.append("command", command);
  if (form === "ingest") {
    const file = document.getElementById("ingest-file").files[0];
    if (file) data.append("file", file);
    data.append("type", document.getElementById("ingest-type").value);
  } else if (form === "folder") {
    data.append("folder", document.getElementById("folder").value.trim());
    data.append("type", document.getElementById("folder-type").value);
  } else if (form === "next") {
    data.append("count", document.getElementById("next-count").value.trim());
  }
  return data;
}

function setBusy(busy) {
  document.querySelectorAll("[data-run],[data-stream]").forEach((b) => (b.disabled = busy));
  stopBtn.classList.toggle("d-none", !busy);
}

// ---- Quick JSON commands ----
function showResult(result) {
  let text = (result.message || (result.ok ? "Done." : "Failed.")) + "\n";
  if (result.data) text += "\n" + JSON.stringify(result.data, null, 2);
  output.textContent = text;
  output.className = result.ok ? "text-success" : "text-danger";
}

function showHealth(result) {
  healthList.innerHTML = "";
  (result.checks || []).forEach((c) => {
    const li = document.createElement("li");
    li.className = "py-1";
    li.innerHTML = `<span class="${c.ok ? "check-ok" : "check-bad"}">${c.ok ? "✓" : "✗"}</span> ${c.label}`;
    healthList.appendChild(li);
  });
  output.textContent = result.ok ? "Setup looks good." : "Setup has problems — see the list above.";
  output.className = result.ok ? "text-success" : "text-danger";
}

async function runJson(btn) {
  const url = btn.dataset.run;
  btn.disabled = true;
  output.textContent = "Working…";
  output.className = "text-secondary";
  try {
    const res = await fetch(url, { method: "POST", body: bodyFor() });
    const result = await res.json();
    if (url === "/api/health") showHealth(result);
    else showResult(result);
  } catch (err) {
    output.textContent = "Request failed: " + err;
    output.className = "text-danger";
  } finally {
    btn.disabled = false;
  }
}

// ---- Long commands: start, then poll the log every second ----
let pollTimer = null;

async function runStream(btn) {
  const command = btn.dataset.stream;
  output.textContent = "";
  output.className = "text-body";
  setBusy(true);

  const res = await fetch("/api/start", { method: "POST", body: bodyFor(btn.dataset.form, command) });
  const started = await res.json();
  if (!started.ok || started.started === false) {
    output.textContent = started.message || "Could not start.";
    output.className = "text-danger";
    setBusy(false);
    return;
  }

  let offset = 0;
  pollTimer = setInterval(async () => {
    try {
      const r = await fetch("/api/logs?offset=" + offset);
      const d = await r.json();
      if (d.lines.length) {
        output.textContent += d.lines.join("\n") + "\n";
        offset = d.offset;
        output.scrollTop = output.scrollHeight;
      }
      if (!d.running) {
        clearInterval(pollTimer);
        pollTimer = null;
        setBusy(false);
      }
    } catch (err) {
      /* transient — keep polling */
    }
  }, 1000);
}

async function stopJob() {
  stopBtn.disabled = true;
  output.textContent += "\n[stopping…]\n";
  try {
    await fetch("/api/stop", { method: "POST" });
  } finally {
    stopBtn.disabled = false;
  }
}

document.querySelectorAll("[data-run]").forEach((b) => b.addEventListener("click", () => runJson(b)));
document.querySelectorAll("[data-stream]").forEach((b) => b.addEventListener("click", () => runStream(b)));
stopBtn.addEventListener("click", stopJob);
