async function loadServices() {
  const select = document.getElementById("service");
  const resp = await fetch("/api/services");
  if (!resp.ok) throw new Error("Не удалось загрузить услуги");
  const rows = await resp.json();
  select.innerHTML = '<option value="">Выберите услугу</option>';
  for (const row of rows) {
    const opt = document.createElement("option");
    opt.value = row.id;
    const price =
      row.price_from === row.price_to
        ? row.price_from
          ? `${row.price_from} ₽`
          : "бесплатно"
        : `${row.price_from}–${row.price_to} ₽`;
    opt.textContent = `${row.name} (${price})`;
    select.appendChild(opt);
  }
}

document.getElementById("order-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("status");
  status.hidden = true;
  const fd = new FormData(e.target);
  const payload = {
    service_id: Number(fd.get("service_id")),
    priority: Number(fd.get("priority") || 2),
    client_name: String(fd.get("client_name") || "").trim(),
    client_email: String(fd.get("client_email") || "").trim(),
    client_phone: String(fd.get("client_phone") || "").trim(),
    comment: String(fd.get("comment") || "").trim(),
  };
  const resp = await fetch("/api/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    status.textContent = data.detail || "Ошибка отправки";
    status.style.background = "#fdecec";
    status.style.color = "#b42318";
    status.hidden = false;
    return;
  }
  status.textContent = data.message || "Заявка отправлена!";
  status.style.background = "#e8f7ee";
  status.style.color = "#0f7b3a";
  status.hidden = false;
  e.target.reset();
  await loadServices();
});

loadServices().catch(() => {
  const status = document.getElementById("status");
  status.textContent = "API недоступен. Запустите docker compose.";
  status.style.background = "#fdecec";
  status.style.color = "#b42318";
  status.hidden = false;
});

function showStatus(el, text, ok) {
  if (!el) return;
  el.textContent = text;
  el.style.background = ok ? "#e8f7ee" : "#fdecec";
  el.style.color = ok ? "#0f7b3a" : "#b42318";
  el.hidden = false;
}

const consultForm = document.getElementById("consult-form");
if (consultForm) {
  consultForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = document.getElementById("consult-status");
    if (status) status.hidden = true;
    const fd = new FormData(consultForm);
    const payload = {
      name: String(fd.get("name") || "").trim(),
      email: String(fd.get("email") || "").trim(),
      phone: String(fd.get("phone") || "").trim(),
      topic: String(fd.get("topic") || "").trim(),
      message: String(fd.get("message") || "").trim(),
    };
    const btn = consultForm.querySelector('button[type="submit"]');
    const prev = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Отправка…";
    }
    try {
      const resp = await fetch("/api/consultation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        showStatus(status, data.detail || "Не удалось отправить заявку.", false);
        return;
      }
      consultForm.reset();
      showStatus(
        status,
        data.message || "Заявка принята. Юрист свяжется с вами в рабочее время.",
        true
      );
    } catch (_) {
      showStatus(status, "Сеть или сервер недоступны.", false);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = prev;
      }
    }
  });
}
