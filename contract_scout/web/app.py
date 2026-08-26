"""Веб: проверка договора, архив, оплата ЮKassa, документы 152‑ФЗ."""

from __future__ import annotations

import html
import logging
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from contract_scout.config import load_settings
from contract_scout.draft import brief_from_form
from contract_scout.ingest import SUPPORTED
from contract_scout.service import ContractScout
from contract_scout.session import COOKIE, issue_cookie, new_visitor_id, parse_cookie
from contract_scout.types import kinds_for_select

logger = logging.getLogger("contract_scout.web")
PKG = Path(__file__).resolve().parent

PAY_RETURN_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"/><title>Оплата — ContractScout</title>
<link rel="stylesheet" href="/static/style.css"/></head>
<body><div class="bg"></div>
<main class="hero"><h1>Возврат из ЮKassa</h1>
<p class="lead">Если оплата прошла, кредиты появятся через несколько секунд. Можно вернуться к проверке договора.</p>
<p><a href="/">На главную</a></p>
<script>
const q = new URLSearchParams(location.search);
const pid = q.get("payment_id") || "";
if (pid) fetch("/api/billing/sync?payment_id=" + encodeURIComponent(pid), {method: "POST"});
else fetch("/api/billing/sync-mine", {method: "POST"});
setTimeout(() => { location.href = "/"; }, 1600);
</script>
</main></body></html>
"""

app = FastAPI(title="ContractScout", version="1.2.0")
_boot = load_settings()
if _boot.trust_proxy:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
_hosts = [h.strip() for h in (_boot.allowed_hosts or "*").split(",") if h.strip()]
if _hosts and _hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts)

app.mount("/static", StaticFiles(directory=PKG / "static"), name="static")

_service: ContractScout | None = None


def service() -> ContractScout:
    global _service
    if _service is None:
        _service = ContractScout(load_settings())
    return _service


def _esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def _legal_page(*, title: str, subtitle: str, body: str) -> HTMLResponse:
    tpl = (PKG / "templates" / "legal.html").read_text(encoding="utf-8")
    html_out = (
        tpl.replace("<!--TITLE-->", _esc(title))
        .replace("<!--SUBTITLE-->", _esc(subtitle))
        .replace("<!--BODY-->", body)
    )
    return HTMLResponse(html_out)


def _privacy_body(s) -> str:
    return f"""
    <h1>Политика обработки персональных данных</h1>
    <p class="muted">Сервис ContractScout. Документ подготовлен под требования 152‑ФЗ. Перед публикацией заполните реквизиты оператора в .env.</p>
    <h2>1. Оператор</h2>
    <p>{_esc(s.operator_name)}<br/>
    ИНН: {_esc(s.operator_inn)} · ОГРН/ОГРНИП: {_esc(s.operator_ogrn)}<br/>
    Адрес: {_esc(s.operator_address)}<br/>
    Email по вопросам ПДн: <a href="mailto:{_esc(s.operator_email)}">{_esc(s.operator_email)}</a></p>
    <h2>2. Какие данные обрабатываем</h2>
    <ul>
      <li>cookie-идентификатор сессии (для учёта кредитов без регистрации);</li>
      <li>email — только при оплате, для фискального чека ЮKassa (54‑ФЗ);</li>
      <li>тексты и файлы договоров, которые вы загружаете для проверки или черновика;</li>
      <li>технические логи запросов (IP, время, путь) на сервере.</li>
    </ul>
    <h2>3. Цели</h2>
    <ul>
      <li>оказание услуги проверки и генерации черновика договора;</li>
      <li>приём оплаты и направление чека;</li>
      <li>обеспечение безопасности и работоспособности сервиса.</li>
    </ul>
    <h2>4. Правовые основания</h2>
    <p>Согласие субъекта ПДн (ст. 6 152‑ФЗ) — при указании email и отметке согласия на форме оплаты;
    исполнение договора-оферты — при использовании сервиса; законные интересы оператора — журналы безопасности.</p>
    <h2>5. Передача третьим лицам</h2>
    <ul>
      <li><strong>ЮKassa</strong> — email и сумма платежа для оплаты и чека;</li>
      <li><strong>провайдер LLM</strong> (например DeepSeek) — только обезличенный текст договора (без ИНН, счетов, адресов и ФИО сторон, если включено обезличивание);</li>
      <li>хостинг / VPS — хранение файлов и журналов на вашем сервере.</li>
    </ul>
    <p>Полные реквизиты сторон в облачный ИИ по умолчанию не отправляются.</p>
    <h2>6. Сроки хранения</h2>
    <ul>
      <li>файлы договоров и архив проектов — до удаления вами или очистки сервера оператором;</li>
      <li>данные платежей — в объёме, нужном для бухгалтерии и споров по оплате;</li>
      <li>email для чека хранит преимущественно ЮKassa; на сервере приложения email в журнал оплат не сохраняется.</li>
    </ul>
    <h2>7. Права субъекта</h2>
    <p>Вы можете запросить сведения об обработке, уточнение, блокирование или удаление данных, отозвать согласие —
    письмом на {_esc(s.operator_email)}. Отзыв согласия не влияет на законность обработки до отзыва.</p>
    <h2>8. Меры защиты</h2>
    <p>HTTPS, ограничение доступа к каталогу data/, секретный ключ cookie, опциональное обезличивание реквизитов перед ИИ.</p>
    <p class="muted">Документ-шаблон. Перед продакшеном согласуйте текст с юристом и зарегистрируйте обработку в РКН при необходимости.</p>
    """


def _offer_body(s) -> str:
    amount = _esc(s.yookassa_amount)
    credits = _esc(str(s.yookassa_credits))
    return f"""
    <h1>Публичная оферта</h1>
    <p class="muted">Договор возмездного оказания услуг сервиса ContractScout. Заполните реквизиты оператора перед публикацией.</p>
    <h2>1. Исполнитель</h2>
    <p>{_esc(s.operator_name)}, ИНН {_esc(s.operator_inn)}, ОГРН/ОГРНИП {_esc(s.operator_ogrn)},
    {_esc(s.operator_address)}, {_esc(s.operator_email)}.</p>
    <h2>2. Предмет</h2>
    <p>Исполнитель предоставляет доступ к веб-сервису проверки договоров и генерации черновиков (в т.ч. с использованием ИИ).
    Результат — вспомогательный материал для переговоров, <strong>не юридическая консультация</strong>.</p>
    <h2>3. Оплата</h2>
    <p>Оплата пакетов кредитов через ЮKassa. По умолчанию: {credits} кредитов за {amount} ₽
    (параметры YOOKASSA_AMOUNT / YOOKASSA_CREDITS). Один кредит — одна проверка ИИ или один черновик/правка ИИ
    при включённом paywall. Загрузка файла и локальный сканер могут быть бесплатными.</p>
    <h2>4. Чек</h2>
    <p>Для оплаты указывается email; чек формирует ЮKassa в соответствии с 54‑ФЗ при настройках магазина.</p>
    <h2>5. Возврат</h2>
    <p>Неиспользованные кредиты по запросу на {_esc(s.operator_email)} в течение 14 дней с оплаты, если услуга
    ИИ по пакету не оказывалась. После списания кредита за оказанную проверку/черновик возврат не производится,
    кроме случаев технической ошибки Исполнителя.</p>
    <h2>6. Принятие оферты</h2>
    <p>Оплата пакета или начало использования платных функций означает акцепт оферты.</p>
    """


@app.middleware("http")
async def visitor_cookie(request: Request, call_next):
    settings = service().settings
    vid = parse_cookie(settings.secret_key, request.cookies.get(COOKIE))
    if not vid:
        vid = new_visitor_id()
    request.state.visitor_id = vid
    response = await call_next(request)
    if request.url.path.startswith("/api/billing/webhook"):
        return response
    response.set_cookie(
        COOKIE,
        issue_cookie(settings.secret_key, vid),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=60 * 60 * 24 * 365,
        path="/",
    )
    return response


def _vid(request: Request) -> str:
    return str(getattr(request.state, "visitor_id", "") or "")


def _billing_public(request: Request | None = None) -> dict:
    s = service().settings
    payload = {
        "paywall": s.paywall_enabled,
        "yookassa": s.yookassa_enabled,
        "amount": s.yookassa_amount,
        "credits_per_pack": s.yookassa_credits,
        "currency": "RUB",
        "credits": 0,
        "require_receipt": s.yookassa_require_receipt,
    }
    if request is not None:
        payload["credits"] = service().billing.credits(_vid(request))
    return payload


def _require_credit(request: Request) -> None:
    if not service().settings.paywall_enabled:
        return
    if not service().billing.try_consume(_vid(request), 1):
        raise HTTPException(
            402,
            f"Нужна оплата: пакет {service().settings.yookassa_credits} проверок за "
            f"{service().settings.yookassa_amount} ₽ через ЮKassa.",
        )


def _refund_credit(request: Request) -> None:
    if service().settings.paywall_enabled:
        service().billing.grant(_vid(request), 1, reason="refund")


def _kind_options(*, selected: str = "") -> str:
    parts = []
    for item in kinds_for_select():
        mark = " selected" if item["id"] == selected else ""
        parts.append(f'<option value="{item["id"]}"{mark}>{item["label"]}</option>')
    return "\n".join(parts)


@app.get("/")
def index():
    page = (PKG / "templates" / "index.html").read_text(encoding="utf-8")
    page = page.replace("<!--KINDS_REVIEW-->", _kind_options(selected="auto"))
    page = page.replace("<!--KINDS_DRAFT-->", _kind_options(selected="it"))
    return HTMLResponse(page)


@app.get("/privacy")
def privacy():
    s = service().settings
    return _legal_page(
        title="Политика ПДн",
        subtitle="152‑ФЗ · обработка персональных данных",
        body=_privacy_body(s),
    )


@app.get("/offer")
def offer():
    s = service().settings
    return _legal_page(
        title="Оферта",
        subtitle="Условия оказания услуг",
        body=_offer_body(s),
    )


@app.get("/health")
def health():
    ping = service().store.ping()
    settings = service().settings
    ping["local_only"] = settings.local_only
    ping["llm_enabled"] = settings.llm_enabled
    ping["redact_requisites"] = settings.redact_requisites
    ping["pinecone"] = service().pinecone.enabled
    ping["projects"] = len(service().list_projects())
    ping["public_base_url"] = bool(settings.public_base_url)
    ping["yookassa"] = settings.yookassa_enabled
    ping["paywall"] = settings.paywall_enabled
    return ping


async def _save_upload(file: UploadFile) -> tuple[Path, str]:
    from contract_scout.ingest import sniff_suffix

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Файл пустой.")
    suffix = sniff_suffix(raw, file.filename or "")
    if suffix not in SUPPORTED:
        raise HTTPException(
            400,
            f"Формат {suffix or '(без расширения)'} не поддерживается. Нужен PDF, DOCX или TXT.",
        )
    dest = service().settings.data_dir / "uploads" / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(raw)
    name = file.filename or dest.name
    if not Path(name).suffix:
        name = f"{Path(name).stem}{suffix}"
    return dest, name


@app.post("/api/review")
async def api_review(
    file: UploadFile | None = File(None),
    text: str = Form(""),
    contract_kind: str = Form("auto"),
):
    pasted = (text or "").strip()
    has_file = bool(file and (file.filename or "").strip())
    if not has_file and len(pasted) < 40:
        raise HTTPException(400, "Загрузите файл PDF/DOCX/TXT или вставьте текст договора.")
    try:
        if has_file:
            dest, filename = await _save_upload(file)
        else:
            dest = service().settings.data_dir / "uploads" / f"{uuid.uuid4().hex}.txt"
            dest.write_text(pasted, encoding="utf-8")
            filename = "contract.txt"
        rec = service().ingest_to_archive(dest, filename=filename, kind=contract_kind)
        return service().get_project(str(rec["id"]))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("archive ingest failed")
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/projects")
def api_projects(q: str = Query("")):
    query = (q or "").strip()
    if not query:
        return {"projects": [], "pinecone": [], "pinecone_enabled": service().pinecone.enabled}
    return service().search_projects(query)


@app.get("/api/projects/{project_id}")
def api_project(project_id: str):
    rec = service().get_project(project_id)
    if rec is None:
        raise HTTPException(404, "Проект не найден")
    return rec


@app.post("/api/projects/{project_id}/ai")
def api_project_ai(project_id: str, request: Request):
    _require_credit(request)
    try:
        rec = service().run_ai_review(project_id)
    except KeyError:
        _refund_credit(request)
        raise HTTPException(404, "Проект не найден") from None
    except Exception as exc:  # noqa: BLE001
        _refund_credit(request)
        logger.exception("ai review failed")
        raise HTTPException(400, str(exc)) from exc
    return service().get_project(str(rec["id"]))


@app.post("/api/projects/{project_id}/fix-risks")
def api_project_fix_risks(project_id: str, request: Request):
    _require_credit(request)
    try:
        data = service().fix_project_risks(project_id)
    except KeyError:
        _refund_credit(request)
        raise HTTPException(404, "Проект не найден") from None
    except Exception as exc:  # noqa: BLE001
        _refund_credit(request)
        logger.exception("fix risks failed")
        raise HTTPException(400, str(exc)) from exc
    data["billing"] = _billing_public(request)
    return data


@app.get("/api/billing")
def api_billing(request: Request):
    return _billing_public(request)


@app.post("/api/billing/checkout")
def api_checkout(request: Request, payload: dict = Body(default={})):
    email = str(payload.get("email") or "").strip()
    consent = bool(payload.get("consent"))
    try:
        data = service().payments.create_checkout(
            visitor_id=_vid(request),
            email=email,
            consent=consent,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("checkout failed")
        raise HTTPException(400, str(exc)) from exc
    return data


@app.post("/api/billing/webhook")
async def api_yookassa_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)
    if not service().settings.yookassa_enabled:
        return JSONResponse({"ok": False, "reason": "disabled"}, status_code=503)
    result = service().payments.handle_notification(body if isinstance(body, dict) else {})
    return result


@app.post("/api/billing/sync")
def api_billing_sync(payment_id: str = Query("")):
    if not payment_id:
        raise HTTPException(400, "payment_id")
    return service().payments.sync_payment(payment_id)


@app.post("/api/billing/sync-mine")
def api_billing_sync_mine(request: Request):
    pid = service().billing.latest_pending(_vid(request))
    if not pid:
        return {"ok": True, "applied": False}
    return service().payments.sync_payment(pid)


@app.get("/pay/return")
def pay_return(payment_id: str = Query("")):
    page = PAY_RETURN_HTML
    if payment_id:
        page = page.replace(
            "const pid = q.get(\"payment_id\") || \"\";",
            f"const pid = q.get(\"payment_id\") || {payment_id!r};",
        )
    return HTMLResponse(page)


@app.get("/api/parties")
def api_parties(q: str = Query("")):
    return {"parties": service().parties.search(q)}


@app.post("/api/draft")
def api_draft(payload: dict, request: Request):
    _require_credit(request)
    brief = brief_from_form(payload)
    try:
        markdown = service().draft(brief)
    except Exception as exc:  # noqa: BLE001
        _refund_credit(request)
        logger.exception("draft failed")
        raise HTTPException(400, str(exc)) from exc
    return {
        "markdown": markdown,
        "privacy": {
            "local_only": service().settings.local_only,
            "sent_to_llm": False if service().settings.local_only else service().settings.llm_enabled,
        },
        "billing": _billing_public(request),
    }


@app.post("/api/draft/revise")
def api_draft_revise(payload: dict, request: Request):
    """Правки статей договора по инструкции пользователя через ИИ."""
    _require_credit(request)
    markdown = str(payload.get("markdown") or "")
    instruction = str(payload.get("instruction") or payload.get("prompt") or "")
    try:
        revised = service().revise_draft(markdown, instruction)
    except Exception as exc:  # noqa: BLE001
        _refund_credit(request)
        logger.exception("draft revise failed")
        raise HTTPException(400, str(exc)) from exc
    return {
        "markdown": revised,
        "billing": _billing_public(request),
        "privacy": {
            "local_only": service().settings.local_only,
            "sent_to_llm": True,
            "note": "В ИИ уходят только статьи без реквизитов сторон (обезличенно).",
        },
    }


@app.post("/api/draft/docx")
def api_draft_docx(payload: dict = Body(...)):
    """Собрать DOCX из (возможно отредактированного) текста + реквизитов формы."""
    markdown = str(payload.get("markdown") or "").strip()
    if len(markdown) < 40:
        raise HTTPException(400, "Сначала сгенерируйте или вставьте текст договора.")
    brief = brief_from_form(payload)
    dest = service().settings.data_dir / "exports" / f"{uuid.uuid4().hex}.docx"
    try:
        service().export_docx(markdown, dest, brief=brief)
    except Exception as exc:  # noqa: BLE001
        logger.exception("docx export failed")
        raise HTTPException(400, str(exc)) from exc
    return FileResponse(
        dest,
        filename="dogovor.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/download/{name}")
def download(name: str):
    path = service().settings.data_dir / "exports" / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "Файл не найден")
    return FileResponse(
        path,
        filename="dogovor.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def main() -> None:
    import uvicorn

    settings = load_settings()
    logging.basicConfig(level=settings.log_level)
    uvicorn.run(
        "contract_scout.web.app:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
        proxy_headers=settings.trust_proxy,
        forwarded_allow_ips="*" if settings.trust_proxy else None,
    )


if __name__ == "__main__":
    main()
