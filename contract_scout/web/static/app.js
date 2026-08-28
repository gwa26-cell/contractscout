const $ = (id) => document.getElementById(id);

const PERSON_FORMS = {
  ooo: {
    name: "Наименование ",
    inn: "ИНН/КПП ",
    address: "Юр. адрес ",
    ogrn: "ОГРН ",
    namePh: "Вектор",
    innPh: "7700000000 / 770001001",
    basis: "Устава",
    repTitle: "Генерального директора",
    face: true,
  },
  ip: {
    name: "ФИО / наименование ИП ",
    inn: "ИНН ",
    address: "Адрес ",
    ogrn: "ОГРНИП ",
    namePh: "ИП Иванов Иван Иванович",
    innPh: "770000000000",
    basis: "листа записи ЕГРИП",
    repTitle: "",
    face: false,
  },
  selfemployed: {
    name: "ФИО ",
    inn: "ИНН ",
    address: "Адрес ",
    ogrn: "",
    namePh: "Иванов Иван Иванович",
    innPh: "770000000000",
    basis: "паспорта гражданина РФ",
    repTitle: "",
    face: false,
  },
  individual: {
    name: "ФИО ",
    inn: "ИНН ",
    address: "Адрес ",
    ogrn: "",
    namePh: "Иванов Иван Иванович",
    innPh: "770000000000",
    basis: "паспорта гражданина РФ",
    repTitle: "",
    face: false,
  },
  custom: {
    name: "Наименование / ФИО ",
    inn: "ИНН / ИНН/КПП ",
    address: "Адрес ",
    ogrn: "ОГРН ",
    namePh: "как в уставе / паспорте",
    innPh: "",
    basis: "Устава",
    repTitle: "Генерального директора",
    face: true,
  },
};

function applyPersonType(box) {
  const key = (box.querySelector(".person-type") || {}).value || "ooo";
  const form = PERSON_FORMS[key] || PERSON_FORMS.ooo;
  const nameLabel = box.querySelector('[data-label="name"]');
  const innLabel = box.querySelector('[data-label="inn"]');
  const addrLabel = box.querySelector('[data-label="address"]');
  const nameInput = box.querySelector(".name-input");
  const innInput = box.querySelector(".inn-input");
  const customRow = box.querySelector(".custom-form");
  const ogrnLabel = box.querySelector('[data-label="ogrn"]');
  const ogrnInput = box.querySelector(".ogrn-input");
  const basisInput = box.querySelector(".basis-input");
  const repTitle = box.querySelector(".rep-title");
  if (nameLabel) nameLabel.firstChild.textContent = form.name;
  if (innLabel) innLabel.firstChild.textContent = form.inn;
  if (addrLabel) addrLabel.firstChild.textContent = form.address;
  if (ogrnLabel) {
    ogrnLabel.classList.toggle("hidden", !form.ogrn);
    if (form.ogrn) ogrnLabel.firstChild.textContent = form.ogrn;
  }
  if (nameInput) nameInput.placeholder = form.namePh;
  if (innInput) innInput.placeholder = form.innPh;
  if (basisInput && !basisInput.dataset.touched) basisInput.placeholder = form.basis || "";
  if (repTitle && !repTitle.value) repTitle.placeholder = form.repTitle || "";
  box.querySelectorAll(".sign-face").forEach((el) => el.classList.toggle("hidden", form.face === false));
  if (customRow) customRow.classList.toggle("hidden", key !== "custom");
}

function fillParty(box, card) {
  if (!card) return;
  const set = (selector, value) => {
    const el = box.querySelector(selector);
    if (el && value != null) el.value = value;
  };
  const typeSel = box.querySelector(".person-type");
  if (typeSel && card.person_type) {
    typeSel.value = card.person_type;
    applyPersonType(box);
  }
  set(".form-label-input", card.form_label || "");
  set(".name-input", card.name || "");
  set(".inn-input", card.inn_kpp || "");
  set(".ogrn-input", card.ogrn || "");
  set(".rep-title", card.rep_title || "");
  set(".rep-name", card.rep || "");
  set(".basis-input", card.basis || "");
  set("[name$='_address']", card.address || "");
  set("[name$='_phone']", card.phone || "");
  set("[name$='_email']", card.email || "");
  set("[name$='_rs']", card.rs || "");
  set("[name$='_bank']", card.bank || "");
  set("[name$='_bik']", card.bik || "");
  set("[name$='_ks']", card.ks || "");
}

function bindPartyLookup(box) {
  const input = box.querySelector(".name-input");
  const list = box.querySelector(".suggest");
  const fileInput = box.querySelector(".party-file-input");
  const fileStatus = box.querySelector(".party-file-status");
  if (!list && !fileInput) return;
  let timer = null;
  const hide = () => {
    if (list) list.classList.add("hidden");
  };

  const runSuggest = (q) => {
    if (!list) return;
    clearTimeout(timer);
    const query = (q || "").trim();
    if (query.length < 2) {
      hide();
      return;
    }
    timer = setTimeout(async () => {
      const resp = await fetch("/api/parties?q=" + encodeURIComponent(query));
      const data = await resp.json();
      const rows = data.parties || [];
      if (!rows.length) {
        hide();
        return;
      }
      list.innerHTML = rows
        .map((p) => {
          const meta = [p.person_type || "", p.inn_kpp || ""].filter(Boolean).join(" · ");
          const label = (p.value || p.name || "").replace(/</g, "&lt;");
          return `<button type="button" data-name="${(p.name || "").replace(/"/g, "&quot;")}">${label} <span>${meta}</span></button>`;
        })
        .join("");
      list.classList.remove("hidden");
      list.querySelectorAll("button").forEach((btn, i) => {
        btn.addEventListener("click", () => {
          fillParty(box, rows[i]);
          hide();
        });
      });
    }, 220);
  };

  if (input) {
    input.addEventListener("input", () => runSuggest(input.value));
    input.addEventListener("blur", () => setTimeout(hide, 200));
  }

  if (fileInput) {
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      if (fileStatus) fileStatus.textContent = "Читаю реквизиты…";
      const fd = new FormData();
      fd.append("file", file);
      try {
        const resp = await fetch("/api/parties/parse", { method: "POST", body: fd });
        const data = await resp.json();
        if (!resp.ok) {
          if (fileStatus) fileStatus.textContent = errText(data);
          return;
        }
        fillParty(box, data.party || {});
        if (fileStatus) {
          const p = data.party || {};
          fileStatus.textContent = `Подставлено: ${p.name || "сторона"}${p.inn_kpp ? " · " + p.inn_kpp : ""}. Сверьте с оригиналом!`;
        }
      } catch (_) {
        if (fileStatus) fileStatus.textContent = "Не удалось прочитать файл.";
      } finally {
        fileInput.value = "";
      }
    });
  }
}

document.querySelectorAll("[data-party]").forEach((box) => {
  const select = box.querySelector(".person-type");
  if (!select) return;
  select.addEventListener("change", () => applyPersonType(box));
  applyPersonType(box);
  bindPartyLookup(box);
});

function severityClass(s) {
  s = (s || "").toLowerCase();
  if (s.includes("crit")) return "crit";
  if (s.includes("high") || s.includes("высок")) return "high";
  if (s.includes("low") || s.includes("низк")) return "low";
  return "medium";
}

function renderReport(data) {
  if (!data) {
    $("review-out").innerHTML = "";
    updateFixButton(null);
    return;
  }
  const items = (data.bottlenecks || [])
    .map(
      (b) => `<div class="item">
        <span class="pill ${severityClass(b.severity)}">${b.severity || ""}</span>
        <h3>${b.title || ""}${b.clause_ref ? ` <span class="clause-ref">${b.clause_ref}</span>` : ""}</h3>
        <p class="quote">${b.quote || ""}</p>
        <p>${b.why || ""}</p>
        <p><strong>Как чинить:</strong> ${b.fix || ""}</p>
      </div>`
    )
    .join("");
  const missing = (data.missing_clauses || [])
    .map((m) => `<li>${m.title || m}${m.why ? " — " + m.why : ""}</li>`)
    .join("");
  const script = (data.negotiate_script || []).map((s) => `<li>${s}</li>`).join("");
  const canFix =
    (data.bottlenecks && data.bottlenecks.length) ||
    (data.missing_clauses && data.missing_clauses.length);
  $("review-out").innerHTML = `
    <div class="score">
      <b>${data.overall_score ?? "—"}</b>
      <div>
        <div class="pill ${severityClass(data.verdict)}">${data.verdict || ""}</div>
        <div class="muted">индекс риска 0–100 · ${data.mode || ""} · ${data.contract_kind_label || ""}</div>
      </div>
    </div>
    <p>${data.summary || ""}</p>
    ${items}
    <h3>Чего может не хватать</h3>
    <ul>${missing}</ul>
    <h3>Что написать контрагенту</h3>
    <ul>${script}</ul>
    ${
      canFix
        ? `<div class="actions fix-risks-actions">
        <button type="button" id="review-fix-btn">Исправить с учётом найденных рисков</button>
      </div>`
        : ""
    }
  `;
  updateFixButton(data);
  const inlineFix = $("review-fix-btn");
  if (inlineFix) inlineFix.addEventListener("click", () => fixCurrentRisks());
}

function updateFixButton(report) {
  const btn = $("archive-fix");
  if (!btn) return;
  const has =
    report &&
    (((report.bottlenecks || []).length > 0) || ((report.missing_clauses || []).length > 0));
  btn.classList.toggle("hidden", !has);
}

function syncDraftEditor(markdown, contractKind) {
  const out = $("draft-out");
  const hint = $("draft-hint");
  const workspace = $("draft-workspace");
  const btn = $("docx-btn");
  if (out) {
    out.value = markdown || "";
    out.readOnly = false;
  }
  if (hint) {
    hint.classList.remove("hidden");
    hint.textContent =
      "Текст исправлен с учётом найденных рисков. Отредактируйте при необходимости и скачайте DOCX.";
  }
  if (workspace) workspace.classList.remove("hidden");
  if (btn) {
    btn.classList.remove("hidden");
    btn.disabled = false;
  }
  if (contractKind) {
    const sel = document.querySelector('#draft-form select[name="contract_kind"]');
    if (sel) {
      const opt = Array.from(sel.options).find((o) => o.value === contractKind);
      if (opt) sel.value = contractKind;
    }
  }
}

function showFixedDraft(markdown, contractKind) {
  const text = (markdown || "").trim();
  const fixWrap = $("fix-workspace");
  const fixedOut = $("fixed-out");
  if (fixWrap) fixWrap.classList.remove("hidden");
  if (fixedOut) {
    fixedOut.value = text;
    fixedOut.readOnly = false;
  }
  syncDraftEditor(text, contractKind);
  if (fixedOut) {
    fixedOut.focus();
    fixWrap?.scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    document.getElementById("draft-workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function downloadMarkdownDocx(markdown, contractKind) {
  const md = (markdown || "").trim();
  if (md.length < 40) {
    alert("Сначала дождитесь исправленного текста.");
    return;
  }
  const fd = new FormData($("draft-form"));
  const payload = Object.fromEntries(fd.entries());
  payload.markdown = md;
  if (contractKind) payload.contract_kind = contractKind;
  const resp = await fetch("/api/draft/docx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    let msg = "Не удалось собрать DOCX";
    try {
      msg = errText(await resp.json());
    } catch (_) {}
    alert(msg);
    return;
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "dogovor.docx";
  a.click();
  URL.revokeObjectURL(url);
}

async function fixCurrentRisks() {
  if (!currentProjectId) return;
  const status = $("review-status");
  const archiveBtn = $("archive-fix");
  const inlineBtn = $("review-fix-btn");
  const fixWrap = $("fix-workspace");
  const fixedOut = $("fixed-out");
  if (status) status.textContent = "Исправляю договор с учётом найденных рисков…";
  if (archiveBtn) archiveBtn.disabled = true;
  if (inlineBtn) inlineBtn.disabled = true;
  if (fixWrap) fixWrap.classList.remove("hidden");
  if (fixedOut) {
    fixedOut.value = "Исправляю текст…";
    fixedOut.readOnly = true;
    fixWrap.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  try {
    const resp = await fetch("/api/projects/" + currentProjectId + "/fix-risks", { method: "POST" });
    const data = await resp.json();
    if (resp.status === 402) {
      if (status) status.textContent = errText(data);
      if (fixedOut) fixedOut.value = "";
      if (fixWrap) fixWrap.classList.add("hidden");
      await refreshBilling();
      return;
    }
    if (!resp.ok) {
      if (status) status.textContent = errText(data);
      if (fixedOut) fixedOut.value = errText(data);
      return;
    }
    showFixedDraft(data.markdown, data.contract_kind);
    window.__lastFixedKind = data.contract_kind || "";
    if (status) {
      status.textContent = "Готово: исправленный договор в редакторе ниже — можно править и скачать DOCX.";
    }
    await refreshBilling();
  } catch (_) {
    if (status) status.textContent = "Не удалось связаться с сервером.";
    if (fixedOut) fixedOut.value = "Ошибка сети.";
  } finally {
    if (archiveBtn) archiveBtn.disabled = false;
    if (inlineBtn) inlineBtn.disabled = false;
  }
}

let currentProjectId = "";
let archiveHits = [];

function statusLabel(row) {
  if (row.is_example) return "пример";
  if (row.status === "ai") return "проверен в ИИ";
  if (row.status === "draft") return "черновик";
  return "в архиве";
}

function setArchiveHint(text) {
  const hint = $("archive-search-hint");
  if (hint) hint.textContent = text || "";
}

function hideArchiveHits() {
  const box = $("archive-hits");
  if (!box) return;
  box.classList.add("hidden");
  box.innerHTML = "";
  archiveHits = [];
}

function fillArchiveHits(rows, q) {
  const box = $("archive-hits");
  if (!box) return;
  archiveHits = rows || [];
  if (!archiveHits.length) {
    hideArchiveHits();
    setArchiveHint(`Нет совпадений для «${q}»`);
    return;
  }
  box.innerHTML = archiveHits
    .map((p) => {
      const title = escapeHtml(p.title || p.filename || p.id);
      const meta = escapeHtml(
        `${statusLabel(p)}${p.overall_score != null ? " · риск " + p.overall_score : ""}${
          p.chars != null ? " · " + p.chars + " симв." : ""
        }`
      );
      const active = p.id === currentProjectId ? " active" : "";
      return `<button type="button" class="archive-hit${active}" data-id="${p.id}">
        <strong>${title}</strong>
        <small>${meta}</small>
      </button>`;
    })
    .join("");
  box.classList.remove("hidden");
  box.querySelectorAll(".archive-hit").forEach((btn) => {
    btn.addEventListener("click", () => openProject(btn.dataset.id));
  });
  setArchiveHint(`Найдено: ${archiveHits.length}. Нажмите строку, чтобы открыть.`);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function searchArchive(q = "") {
  const query = (q || "").trim();
  if (!query) {
    hideArchiveHits();
    setArchiveHint("Введите хотя бы 1 символ — появятся совпадения");
    return;
  }
  setArchiveHint("Ищу…");
  try {
    const resp = await fetch("/api/projects?q=" + encodeURIComponent(query));
    if (!resp.ok) {
      hideArchiveHits();
      setArchiveHint("Ошибка поиска: " + resp.status);
      return;
    }
    const data = await resp.json();
    fillArchiveHits(data.projects || [], query);
  } catch (err) {
    hideArchiveHits();
    setArchiveHint("Не удалось выполнить поиск");
  }
}

async function openProject(id) {
  currentProjectId = id;
  const resp = await fetch("/api/projects/" + id);
  const data = await resp.json();
  if (!resp.ok) {
    $("review-status").textContent = data.detail || "Не найден";
    return;
  }
  $("archive-detail").classList.remove("hidden");
  $("archive-text").textContent = data.text || "";
  $("archive-ai").disabled = data.kind === "draft";
  $("archive-ai").textContent = data.kind === "draft" ? "Черновик без проверки ИИ" : "Проверить в ИИ";
  const report = data.report || {};
  if (report.privacy) {
    const n = report.privacy.requisites_redacted ?? report.requisites_redacted ?? 0;
    const llm = report.mode === "hybrid" ? "разбор в ИИ без реквизитов" : "локальный сканер, ИИ ещё не запускался";
    $("review-status").textContent = `${data.filename}: ${llm}; вырезано реквизитов: ${n}. ` + (report.disclaimer || "");
  } else {
    $("review-status").textContent = data.filename || "";
  }
  if (data.kind === "draft") {
    $("review-out").innerHTML = "";
    updateFixButton(null);
    if ($("fix-workspace")) $("fix-workspace").classList.add("hidden");
  } else {
    renderReport({ ...report, contract_kind_label: data.contract_kind_label });
  }
  const lib = (report && report.library) || {};
  const libEl = $("archive-library");
  if (libEl) {
    libEl.textContent = lib.note
      ? lib.note
      : data.is_example
        ? "Этот договор сохранён как удачный пример для шаблонов."
        : "";
  }
  const q = ($("archive-q") && $("archive-q").value.trim()) || "";
  if (q) {
    await searchArchive(q);
  } else if ((data.title || data.filename) && $("archive-q")) {
    const label = data.title || data.filename;
    $("archive-q").value = label;
    fillArchiveHits(
      [
        {
          id: data.id,
          filename: data.filename,
          title: data.title || data.filename,
          status: data.status,
          is_example: data.is_example,
          overall_score: (data.report && data.report.overall_score) ?? data.overall_score,
          chars: data.chars,
        },
      ],
      label
    );
  }
}

$("review-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const fileInput = form.querySelector('[name="file"]');
  const textInput = form.querySelector('[name="text"]');
  const hasFile = fileInput && fileInput.files && fileInput.files.length > 0;
  const pasted = (textInput && textInput.value.trim()) || "";
  if (!hasFile && pasted.length < 40) {
    $("review-status").textContent = "Загрузите файл PDF/DOCX/TXT или вставьте текст договора.";
    return;
  }
  const fd = new FormData(form);
  if (!hasFile) fd.delete("file");
  $("review-status").textContent = "Разбираю договор…";
  $("review-out").innerHTML = "";
  const resp = await fetch("/api/review", { method: "POST", body: fd });
  const data = await resp.json();
  if (!resp.ok) {
    $("review-status").textContent = data.detail || "Ошибка загрузки";
    return;
  }
  await openProject(data.id);
  document.getElementById("archive")?.scrollIntoView({ behavior: "smooth", block: "start" });
});

let archiveTimer = null;
const archiveQ = $("archive-q");
if (archiveQ) {
  archiveQ.addEventListener("input", () => {
    clearTimeout(archiveTimer);
    const q = archiveQ.value.trim();
    if (!q) {
      hideArchiveHits();
      setArchiveHint("Введите хотя бы 1 символ — появятся совпадения");
      return;
    }
    archiveTimer = setTimeout(() => searchArchive(q), 120);
  });
  archiveQ.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      clearTimeout(archiveTimer);
      searchArchive(archiveQ.value.trim());
    }
  });
}
hideArchiveHits();
setArchiveHint("Введите хотя бы 1 символ — появятся совпадения");
$("archive-ai").addEventListener("click", async () => {
  if (!currentProjectId) return;
  $("review-status").textContent = "Отправляю обезличенный текст в ИИ…";
  const resp = await fetch("/api/projects/" + currentProjectId + "/ai", { method: "POST" });
  const data = await resp.json();
  if (resp.status === 402) {
    $("review-status").textContent = errText(data);
    await refreshBilling();
    return;
  }
  if (!resp.ok) {
    $("review-status").textContent = errText(data);
    return;
  }
  await openProject(data.id);
  await refreshBilling();
  const report = (data.report) || {};
  const lib = report.library || {};
  if (lib.note && $("archive-library")) {
    $("archive-library").textContent = lib.note;
  }
});
if ($("archive-fix")) {
  $("archive-fix").addEventListener("click", () => fixCurrentRisks());
}
if ($("fixed-docx-btn")) {
  $("fixed-docx-btn").addEventListener("click", async () => {
    const btn = $("fixed-docx-btn");
    const prev = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Собираю DOCX…";
    try {
      await downloadMarkdownDocx(($("fixed-out") && $("fixed-out").value) || "", window.__lastFixedKind || "");
    } finally {
      btn.disabled = false;
      btn.textContent = prev;
    }
  });
}
if ($("fixed-to-draft")) {
  $("fixed-to-draft").addEventListener("click", () => {
    const md = ($("fixed-out") && $("fixed-out").value) || "";
    syncDraftEditor(md, window.__lastFixedKind || "");
    document.getElementById("draft-workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
    $("draft-out")?.focus();
  });
}
function errText(data) {
  const d = data && data.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d[0] && d[0].msg) return d[0].msg;
  return "Ошибка";
}

async function refreshBilling() {
  const resp = await fetch("/api/billing");
  const data = await resp.json();
  const bar = $("pay-bar");
  if (!bar) return data;
  if (!data.yookassa && !data.paywall) {
    bar.classList.add("hidden");
    return data;
  }
  bar.classList.remove("hidden");
  $("pay-status").textContent = data.paywall
    ? `ИИ и черновик: ${data.credits} кр. · пакет ${data.credits_per_pack} за ${data.amount} ₽`
    : `ЮKassa подключена. Кредиты: ${data.credits}`;
  const emailWrap = document.querySelector(".pay-email");
  const consentWrap = document.querySelector(".pay-consent");
  if (emailWrap) emailWrap.classList.toggle("hidden", !data.yookassa);
  if (consentWrap) consentWrap.classList.toggle("hidden", !data.yookassa);
  if ($("pay-btn")) $("pay-btn").classList.toggle("hidden", !data.yookassa);
  return data;
}

if ($("pay-btn")) {
  $("pay-btn").addEventListener("click", async () => {
    const email = ($("pay-email") && $("pay-email").value.trim()) || "";
    const consent = !!($("pay-consent") && $("pay-consent").checked);
    if (!email || !email.includes("@")) {
      $("pay-status").textContent = "Укажите email для чека ЮKassa.";
      return;
    }
    if (!consent) {
      $("pay-status").textContent = "Нужно согласие на обработку email (152‑ФЗ).";
      return;
    }
    $("pay-status").textContent = "Создаю платёж в ЮKassa…";
    const resp = await fetch("/api/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, consent: true }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      $("pay-status").textContent = errText(data);
      return;
    }
    window.location.href = data.confirmation_url;
  });
}
refreshBilling();

$("draft-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const payload = Object.fromEntries(fd.entries());
  const out = $("draft-out");
  const btn = $("docx-btn");
  const hint = $("draft-hint");
  const workspace = $("draft-workspace");
  out.readOnly = true;
  out.value = "Собираю защитный черновик…";
  if (workspace) workspace.classList.remove("hidden");
  if (btn) {
    btn.classList.add("hidden");
    btn.disabled = true;
  }
  if (hint) hint.classList.add("hidden");
  const resp = await fetch("/api/draft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await resp.json();
  if (resp.status === 402) {
    out.value = errText(data);
    await refreshBilling();
    return;
  }
  if (!resp.ok) {
    out.value = errText(data);
    return;
  }
  out.value = data.markdown || "";
  out.readOnly = false;
  out.focus();
  if (hint) hint.classList.remove("hidden");
  if (workspace) workspace.classList.remove("hidden");
  if (btn) {
    btn.classList.remove("hidden");
    btn.disabled = false;
  }
  if ($("draft-ai-status")) $("draft-ai-status").textContent = "";
});

if ($("docx-btn")) {
$("docx-btn").addEventListener("click", async () => {
  const btn = $("docx-btn");
  const out = $("draft-out");
  const markdown = (out.value || "").trim();
  if (markdown.length < 40 || out.readOnly) {
    out.value = "Сначала сгенерируйте черновик.";
    return;
  }
  const fd = new FormData($("draft-form"));
  const payload = Object.fromEntries(fd.entries());
  payload.markdown = out.value;
  const prev = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Собираю DOCX…";
  try {
    const resp = await fetch("/api/draft/docx", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      let msg = "Не удалось собрать DOCX";
      try {
        const data = await resp.json();
        msg = errText(data);
      } catch (_) {}
      alert(msg);
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dogovor.docx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } finally {
    btn.disabled = false;
    btn.textContent = prev;
  }
});
}

function clearDraftForm() {
  const form = $("draft-form");
  if (!form) return;
  form.reset();
  form.querySelectorAll("input, textarea").forEach((el) => {
    if (el.type === "checkbox" || el.type === "radio") {
      el.checked = false;
      return;
    }
    if (el.type === "file") {
      el.value = "";
      return;
    }
    if (el.tagName === "SELECT") return;
    el.value = "";
  });
  form.querySelectorAll(".person-type").forEach((sel) => {
    sel.value = "ooo";
  });
  const kindSel = form.querySelector('select[name="contract_kind"]');
  if (kindSel && kindSel.options.length) {
    const it = Array.from(kindSel.options).find((o) => o.value === "it");
    kindSel.value = it ? "it" : kindSel.options[0].value;
  }
  document.querySelectorAll("[data-party]").forEach((box) => {
    applyPersonType(box);
    const st = box.querySelector(".party-file-status");
    if (st) st.textContent = "";
    const suggest = box.querySelector(".suggest");
    if (suggest) {
      suggest.classList.add("hidden");
      suggest.innerHTML = "";
    }
  });
  if ($("contract-date-display")) $("contract-date-display").value = "";
  if ($("contract-date-picker")) $("contract-date-picker").value = "";
  if ($("contract-date")) $("contract-date").value = "";
  const out = $("draft-out");
  if (out) {
    out.value = "";
    out.readOnly = true;
  }
  if ($("draft-hint")) $("draft-hint").classList.add("hidden");
  if ($("draft-workspace")) $("draft-workspace").classList.add("hidden");
  if ($("docx-btn")) {
    $("docx-btn").classList.add("hidden");
    $("docx-btn").disabled = true;
  }
  if ($("draft-ai-prompt")) $("draft-ai-prompt").value = "";
  if ($("draft-ai-status")) $("draft-ai-status").textContent = "";
}

if ($("draft-clear")) {
  $("draft-clear").addEventListener("click", () => clearDraftForm());
}

if ($("draft-ai-btn")) {
$("draft-ai-btn").addEventListener("click", async () => {
  const out = $("draft-out");
  const prompt = $("draft-ai-prompt");
  const status = $("draft-ai-status");
  const btn = $("draft-ai-btn");
  const instruction = (prompt.value || "").trim();
  if ((out.value || "").trim().length < 40 || out.readOnly) {
    status.textContent = "Сначала сгенерируйте черновик.";
    return;
  }
  if (instruction.length < 3) {
    status.textContent = "Опишите, что добавить или убрать.";
    prompt.focus();
    return;
  }
  const prev = btn.textContent;
  btn.disabled = true;
  btn.textContent = "ИИ правит…";
  status.textContent = "Отправляю статьи в ИИ без реквизитов…";
  try {
    const resp = await fetch("/api/draft/revise", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: out.value, instruction }),
    });
    const data = await resp.json();
    if (resp.status === 402) {
      status.textContent = errText(data);
      await refreshBilling();
      return;
    }
    if (!resp.ok) {
      status.textContent = errText(data);
      return;
    }
    out.value = data.markdown || out.value;
    status.textContent = "Готово — проверьте текст слева и скачайте DOCX.";
    out.focus();
  } catch (err) {
    status.textContent = "Сеть или сервер недоступны.";
  } finally {
    btn.disabled = false;
    btn.textContent = prev;
  }
});
}

(() => {
  const display = $("contract-date-display");
  const hidden = $("contract-date");
  const picker = $("contract-date-picker");
  const calBtn = $("contract-date-cal");
  if (!display || !hidden || !picker) return;

  function isoToRu(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    if (!m) return "";
    return `${m[3]}.${m[2]}.${m[1]}`;
  }

  function ruToIso(ru) {
    const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec((ru || "").trim());
    if (!m) return "";
    const d = Number(m[1]);
    const mo = Number(m[2]);
    const y = Number(m[3]);
    const dt = new Date(y, mo - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return "";
    return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }

  function syncFromDisplay() {
    const iso = ruToIso(display.value);
    hidden.value = iso;
    if (iso) picker.value = iso;
  }

  function syncFromPicker() {
    const iso = picker.value || "";
    hidden.value = iso;
    display.value = isoToRu(iso);
  }

  display.addEventListener("input", () => {
    let v = display.value.replace(/[^\d.]/g, "");
    if (v.length > 10) v = v.slice(0, 10);
    // автоточки: ДД.ММ.ГГГГ
    const digits = v.replace(/\./g, "");
    let out = digits;
    if (digits.length > 4) out = `${digits.slice(0, 2)}.${digits.slice(2, 4)}.${digits.slice(4, 8)}`;
    else if (digits.length > 2) out = `${digits.slice(0, 2)}.${digits.slice(2)}`;
    display.value = out;
    syncFromDisplay();
  });

  display.addEventListener("blur", syncFromDisplay);
  picker.addEventListener("change", syncFromPicker);

  function openCal() {
    try {
      if (typeof picker.showPicker === "function") picker.showPicker();
      else picker.click();
    } catch (_) {
      picker.focus();
    }
  }
  if (calBtn) calBtn.addEventListener("click", openCal);
})();

const consultForm = $("consult-form");
if (consultForm) {
  consultForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = $("consult-status");
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
        if (status) {
          status.textContent = errText(data) || "Не удалось отправить заявку.";
          status.className = "status err";
          status.hidden = false;
        }
        return;
      }
      consultForm.reset();
      if (status) {
        status.textContent =
          data.message || "Заявка принята. Юрист свяжется с вами в рабочее время.";
        status.className = "status ok";
        status.hidden = false;
      }
    } catch (_) {
      if (status) {
        status.textContent = "Сеть или сервер недоступны.";
        status.className = "status err";
        status.hidden = false;
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = prev;
      }
    }
  });
}

(() => {
  const params = new URLSearchParams(window.location.search || "");
  const openDraft =
    params.get("open") === "draft" ||
    (window.location.hash || "").replace(/^#/, "") === "draft";
  if (!openDraft) return;
  const section = document.getElementById("draft");
  if (!section) return;
  requestAnimationFrame(() => {
    section.scrollIntoView({ behavior: "smooth", block: "start" });
  });
})();
