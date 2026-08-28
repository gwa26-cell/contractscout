const tokenKey = "cs_admin_token";

function token() {
  return localStorage.getItem(tokenKey) || "";
}

function setToken(value) {
  if (value) localStorage.setItem(tokenKey, value);
  else localStorage.removeItem(tokenKey);
}

function authHeaders() {
  const t = token();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function api(path, options = {}) {
  const resp = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}

const authPanel = document.getElementById("auth-panel");
const adminPanel = document.getElementById("admin-panel");
const registerForm = document.getElementById("register-form");
const loginForm = document.getElementById("login-form");
const authStatus = document.getElementById("auth-status");
const userLabel = document.getElementById("user-label");
const logoutBtn = document.getElementById("logout-btn");
const statsBtn = document.getElementById("stats-btn");

function showAuth(message = "") {
  authPanel.classList.remove("hidden");
  adminPanel.classList.add("hidden");
  logoutBtn.hidden = true;
  statsBtn.hidden = true;
  registerForm.classList.remove("hidden");
  if (message) {
    authStatus.textContent = message;
    authStatus.hidden = false;
  } else {
    authStatus.hidden = true;
  }
}

function showAdmin(email) {
  authPanel.classList.add("hidden");
  adminPanel.classList.remove("hidden");
  registerForm.classList.add("hidden");
  logoutBtn.hidden = false;
  statsBtn.hidden = false;
  userLabel.textContent = email ? `· ${email}` : "";
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(loginForm);
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: fd.get("email"),
        password: fd.get("password"),
      }),
    });
    setToken(data.access_token);
    const me = await api("/api/auth/me");
    showAdmin(me.email);
    await refreshAll();
  } catch (err) {
    authStatus.textContent = err.message;
    authStatus.hidden = false;
  }
});

registerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(registerForm);
  try {
    await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email: fd.get("email"),
        password: fd.get("password"),
      }),
    });
    authStatus.textContent = "Регистрация успешна. Войдите.";
    authStatus.hidden = false;
    registerForm.classList.add("hidden");
  } catch (err) {
    authStatus.textContent = err.message;
    authStatus.hidden = false;
  }
});

logoutBtn.addEventListener("click", () => {
  setToken("");
  showAuth();
});

const servicesBody = document.querySelector("#services-table tbody");
const ordersBody = document.querySelector("#orders-table tbody");
const serviceForm = document.getElementById("service-form");
const orderDetail = document.getElementById("order-detail");

function field(name) {
  return serviceForm.elements.namedItem(name);
}

async function loadServices() {
  const rows = await api("/api/services");
  servicesBody.innerHTML = rows
    .map(
      (r) => `<tr data-id="${r.id}">
        <td>${r.id}</td>
        <td>${r.name}</td>
        <td>${r.price_from}–${r.price_to}</td>
        <td><button type="button" class="ghost pick-service">Выбрать</button></td>
      </tr>`
    )
    .join("");
}

servicesBody.addEventListener("click", async (e) => {
  const btn = e.target.closest(".pick-service");
  if (!btn) return;
  const id = Number(btn.closest("tr").dataset.id);
  const row = await api(`/api/services`).then((rows) => rows.find((x) => x.id === id));
  if (!row) return;
  field("id").value = row.id;
  field("name").value = row.name;
  field("description").value = row.description || "";
  field("price_from").value = row.price_from;
  field("price_to").value = row.price_to;
});

document.getElementById("new-service").addEventListener("click", () => {
  serviceForm.reset();
  field("id").value = "";
});

serviceForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(serviceForm);
  const payload = {
    name: fd.get("name"),
    description: fd.get("description"),
    price_from: Number(fd.get("price_from") || 0),
    price_to: Number(fd.get("price_to") || 0),
  };
  const id = fd.get("id");
  if (id) {
    await api(`/api/services/${id}`, { method: "PUT", body: JSON.stringify(payload) });
  } else {
    await api("/api/services", { method: "POST", body: JSON.stringify(payload) });
  }
  await loadServices();
});

document.getElementById("delete-service").addEventListener("click", async () => {
  const id = field("id").value;
  if (!id) return;
  await api(`/api/services/${id}`, { method: "DELETE" });
  serviceForm.reset();
  await loadServices();
});

async function loadOrders() {
  const rows = await api("/api/orders");
  ordersBody.innerHTML = rows
    .map(
      (r) => `<tr>
        <td>${r.id}</td>
        <td>${r.priority}</td>
        <td>${r.lead_temperature}</td>
        <td>${r.service_name || r.service_id}</td>
        <td>${r.client_name}</td>
        <td><button type="button" class="ghost view-order" data-id="${r.id}">Просмотр</button></td>
      </tr>`
    )
    .join("");
}

ordersBody.addEventListener("click", async (e) => {
  const btn = e.target.closest(".view-order");
  if (!btn) return;
  const row = await api(`/api/orders/${btn.dataset.id}`);
  orderDetail.textContent = JSON.stringify(row, null, 2);
  orderDetail.classList.remove("hidden");
});

const statsModal = document.getElementById("stats-modal");
statsBtn.addEventListener("click", async () => {
  const stats = await api("/api/behavior-metrics/stats");
  document.getElementById("avg-day").textContent = Math.round(stats.avg_time_day_sec);
  document.getElementById("avg-week").textContent = Math.round(stats.avg_time_week_sec);
  document.getElementById("avg-month").textContent = Math.round(stats.avg_time_month_sec);
  drawHeatmap(stats.heatmap || []);
  statsModal.classList.remove("hidden");
});
document.getElementById("close-stats").addEventListener("click", () => {
  statsModal.classList.add("hidden");
});

function drawHeatmap(points) {
  const canvas = document.getElementById("heatmap");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#f4f6fb";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!points.length) return;
  const max = Math.max(...points.map((p) => p.count));
  for (const p of points) {
    const alpha = 0.15 + (p.count / max) * 0.85;
    const radius = 6 + (p.count / max) * 18;
    ctx.beginPath();
    ctx.fillStyle = `rgba(47, 111, 237, ${alpha})`;
    ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
    ctx.fill();
  }
}

async function refreshAll() {
  await loadServices();
  await loadOrders();
}

(async function boot() {
  if (!token()) {
    showAuth();
    return;
  }
  try {
    const me = await api("/api/auth/me");
    showAdmin(me.email);
    await refreshAll();
  } catch (_) {
    setToken("");
    showAuth();
  }
})();
