"""MAX-бот: загрузка договора → отчёт; мастер проекта договора."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contract_scout.config import Settings, load_settings, ssl_verify
from contract_scout.ingest import SUPPORTED, sniff_suffix
from contract_scout.service import ContractScout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("contract_scout.bot")

START_TEXT = (
    "Привет! Я ContractScout — проверяю договоры и веду к веб-форме проекта.\n\n"
    "• «Проверить договор» — пришлите PDF/DOCX/TXT или вставьте текст договора\n"
    "• «Проект договора» — открою веб-версию: реквизиты, подписанты, скачивание DOCX\n"
    "• /help — справка\n\n"
    "Это не юридическая консультация."
)

REVIEW_PROMPT = (
    "Пришлите договор для проверки:\n"
    "• файл PDF, DOCX или TXT, или\n"
    "• текст договора прямо сообщением.\n\n"
    "В чат вернётся краткое резюме, полный отчёт — файлом."
)

_GREETINGS = {
    "привет",
    "здравствуй",
    "здравствуйте",
    "добрый день",
    "добрый вечер",
    "доброе утро",
    "хай",
    "hello",
    "hi",
    "ку",
    "хелло",
}


def _auth(settings: Settings) -> Dict[str, str]:
    return {"Authorization": settings.max_bot_token}


def _command_name(text: str) -> str:
    first = (text or "").strip().split()[0] if text else ""
    if not first.startswith("/"):
        return ""
    return first.split("@")[0].lower()


def action_keyboard(web_draft_url: str = "") -> List[Dict[str, Any]]:
    draft_btn: Dict[str, Any]
    if web_draft_url:
        draft_btn = {"type": "link", "text": "Проект договора (веб)", "url": web_draft_url}
    else:
        draft_btn = {"type": "callback", "text": "Проект договора", "payload": "draft"}
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {"type": "callback", "text": "Проверить договор", "payload": "review"},
                        draft_btn,
                    ]
                ]
            },
        }
    ]


def format_report(report: Dict[str, Any], *, limit: int = 3500) -> str:
    lines = [
        f"Файл: {report.get('filename')}",
        f"Тип: {report.get('contract_kind_label') or report.get('contract_kind')}",
        f"Индекс риска: {report.get('overall_score')}/100 — {report.get('verdict')}",
        "",
        str(report.get("summary") or ""),
        "",
        "Узкие места:",
    ]
    for item in (report.get("bottlenecks") or [])[:8]:
        lines.append(f"• [{item.get('severity')}] {item.get('title')}")
        if item.get("fix"):
            lines.append(f"  → {item['fix']}")
    missing = report.get("missing_clauses") or []
    if missing:
        lines.append("\nПробелы:")
        for m in missing[:6]:
            title = m.get("title") if isinstance(m, dict) else str(m)
            lines.append(f"• {title}")
    lines.append("\nПолный отчёт — во вложении.")
    lines.append(str(report.get("disclaimer") or ""))
    text = "\n".join(lines)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class ContractMaxBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.scout = ContractScout(settings)
        self._waiting: Dict[int, str] = {}

    def _web_base(self) -> str:
        base = (self.settings.public_base_url or "").rstrip("/")
        if base:
            return base
        host = self.settings.web_host if self.settings.web_host not in {"0.0.0.0", "::"} else "127.0.0.1"
        return f"http://{host}:{self.settings.web_port}"

    def _web_draft_url(self) -> str:
        return f"{self._web_base()}/#draft"

    def _keyboard(self) -> List[Dict[str, Any]]:
        return action_keyboard(self._web_draft_url())

    async def _send(
        self,
        *,
        text: str,
        user_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        with_keyboard: bool = True,
    ) -> None:
        params: Dict[str, Any] = {}
        if chat_id is not None:
            params["chat_id"] = chat_id
        elif user_id is not None:
            params["user_id"] = user_id
        atts: List[Dict[str, Any]] = list(attachments or [])
        if with_keyboard:
            atts.extend(self._keyboard())
        body: Dict[str, Any] = {
            "text": (text or "")[:4000],
            "notify": True,
        }
        if atts:
            body["attachments"] = atts
        last_error = ""
        async with httpx.AsyncClient(timeout=90.0, verify=ssl_verify()) as client:
            for attempt in range(6):
                resp = await client.post(
                    f"{self.settings.max_api_base}/messages",
                    params=params,
                    headers={**_auth(self.settings), "Content-Type": "application/json"},
                    json=body,
                )
                if resp.status_code < 400:
                    return
                last_error = resp.text[:400]
                if resp.status_code == 400 and "attachment.not.ready" in last_error:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                logger.error("MAX send failed: %s %s", resp.status_code, last_error)
                resp.raise_for_status()
        raise RuntimeError(f"MAX send failed after retries: {last_error}")

    async def _offer_web_draft(self, user_id: Optional[int], chat_id: Optional[int]) -> None:
        url = self._web_draft_url()
        await self._send(
            user_id=user_id,
            chat_id=chat_id,
            text=(
                "Чтобы составить договор с реквизитами, подписантами и скачать DOCX, "
                f"откройте веб-версию:\n{url}\n\n"
                "В боте удобнее только проверка: пришлите файл или текст договора."
            ),
        )

    async def _review_path(
        self, user_id: int, chat_id: Optional[int], path: Path, filename: str
    ) -> None:
        self._waiting.pop(user_id, None)
        await self._send(user_id=user_id, chat_id=chat_id, text="Документ на проверке, это займёт минуту…")
        report = await asyncio.to_thread(
            self.scout.ingest_and_review,
            path,
            user_id=str(user_id),
            filename=filename,
            kind="auto",
        )
        report_path = await asyncio.to_thread(
            self.scout.report_to_file, report, stem=Path(filename).stem or "review"
        )
        await self._send_file(
            report_path,
            user_id=user_id,
            chat_id=chat_id,
            text=format_report(report),
        )

    async def _upload_file(self, path: Path) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=120.0, verify=ssl_verify()) as client:
            resp = await client.post(
                f"{self.settings.max_api_base}/uploads",
                params={"type": "file"},
                headers=_auth(self.settings),
            )
            resp.raise_for_status()
            meta = resp.json()
            upload_url = str(meta.get("url") or "")
            if not upload_url:
                raise RuntimeError(f"MAX /uploads без url: {meta}")
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            with path.open("rb") as fh:
                put = await client.post(
                    upload_url,
                    files={"data": (path.name, fh, mime)},
                )
            put.raise_for_status()
            payload = put.json() if put.content else {}
        token = None
        if isinstance(payload, dict):
            token = payload.get("token")
            if not token and isinstance(payload.get("payload"), dict):
                token = payload["payload"].get("token")
        token = token or meta.get("token")
        if not token:
            raise RuntimeError(f"MAX file upload без token: {payload or meta}")
        return {"type": "file", "payload": {"token": token}}

    async def _send_file(
        self,
        path: Path,
        *,
        text: str,
        user_id: Optional[int] = None,
        chat_id: Optional[int] = None,
    ) -> None:
        att = await self._upload_file(path)
        await asyncio.sleep(1.0)
        await self._send(
            user_id=user_id,
            chat_id=chat_id,
            text=text,
            attachments=[att],
            with_keyboard=True,
        )

    async def _answer_callback(self, callback_id: str, notification: str = "Ок") -> None:
        async with httpx.AsyncClient(timeout=30.0, verify=ssl_verify()) as client:
            await client.post(
                f"{self.settings.max_api_base}/answers",
                params={"callback_id": callback_id},
                headers={**_auth(self.settings), "Content-Type": "application/json"},
                json={"notification": notification[:200]},
            )

    @staticmethod
    def _message_text(message: Dict[str, Any]) -> str:
        body = message.get("body") or {}
        return (body.get("text") or message.get("text") or "").strip()

    @staticmethod
    def _attachments(message: Dict[str, Any]) -> List[Dict[str, Any]]:
        body = message.get("body") or {}
        raw = body.get("attachments") or message.get("attachments") or []
        return [item for item in raw if isinstance(item, dict)]

    @staticmethod
    def _sender_user_id(update: Dict[str, Any], message: Dict[str, Any]) -> Optional[int]:
        recipient = message.get("recipient") if isinstance(message, dict) else {}
        nodes = [
            message.get("sender") if isinstance(message, dict) else None,
            message.get("from") if isinstance(message, dict) else None,
            message.get("user") if isinstance(message, dict) else None,
            update.get("sender"),
            update.get("user"),
            recipient if isinstance(recipient, dict) else None,
            (recipient or {}).get("user") if isinstance(recipient, dict) else None,
        ]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("user_id") is not None:
                return int(node["user_id"])
            if node.get("id") is not None:
                return int(node["id"])
        return None

    @staticmethod
    def _chat_id(message: Dict[str, Any]) -> Optional[int]:
        recipient = message.get("recipient") or {}
        if recipient.get("chat_id") is not None:
            return int(recipient["chat_id"])
        if message.get("chat_id") is not None:
            return int(message["chat_id"])
        return None

    @staticmethod
    def _sender_is_bot(message: Dict[str, Any]) -> bool:
        sender = message.get("sender") or {}
        return bool(sender.get("is_bot") or sender.get("bot"))

    async def _download(self, url: str, dest: Path) -> None:
        async with httpx.AsyncClient(timeout=120.0, verify=ssl_verify()) as client:
            resp = await client.get(url, headers=_auth(self.settings))
            resp.raise_for_status()
            dest.write_bytes(resp.content)

    async def _handle_files(self, user_id: int, chat_id: Optional[int], attachments: List[Dict[str, Any]]) -> bool:
        handled = False
        for item in attachments:
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            att_type = str(item.get("type") or payload.get("type") or "").lower()
            if att_type in {
                "image",
                "sticker",
                "audio",
                "video",
                "location",
                "contact",
                "inline_keyboard",
                "share",
                "keyboard",
            }:
                continue
            url = (
                payload.get("url")
                or payload.get("fileUrl")
                or payload.get("file_url")
                or item.get("url")
                or item.get("fileUrl")
                or item.get("file_url")
            )
            name = (
                payload.get("filename")
                or payload.get("fileName")
                or payload.get("file_name")
                or payload.get("name")
                or item.get("filename")
                or item.get("fileName")
                or item.get("name")
                or "contract"
            )
            if isinstance(name, str) and "%" in name:
                name = unquote(name)
            if not url:
                logger.info("skip attachment without url keys=%s payload=%s", list(item)[:12], list(payload)[:12])
                continue
            dest_dir = self.settings.data_dir / "uploads"
            dest_dir.mkdir(parents=True, exist_ok=True)
            tmp = dest_dir / f"{user_id}_{Path(str(name)).stem or 'contract'}.bin"
            try:
                await self._download(str(url), tmp)
            except Exception as exc:  # noqa: BLE001
                logger.exception("download failed: %s", exc)
                await self._send(
                    user_id=user_id,
                    chat_id=chat_id,
                    text="Не удалось скачать файл из MAX. Пришлите ещё раз или загрузите на сайте.",
                )
                continue
            raw = tmp.read_bytes()[:8192]
            suffix = sniff_suffix(raw, str(name))
            if not suffix:
                suffix = Path(urlparse(str(url)).path).suffix.lower()
            if suffix not in SUPPORTED:
                tmp.unlink(missing_ok=True)
                await self._send(
                    user_id=user_id,
                    chat_id=chat_id,
                    text=f"Формат {suffix or '(без расширения)'} не поддерживается. Нужен PDF, DOCX или TXT.",
                )
                continue
            safe_stem = Path(str(name)).stem or "contract"
            dest = dest_dir / f"{user_id}_{safe_stem}{suffix}"
            if dest != tmp:
                if dest.exists():
                    dest.unlink()
                tmp.replace(dest)
            display_name = str(name) if Path(str(name)).suffix else f"{safe_stem}{suffix}"
            logger.info("accepted file name=%s sniff=%s size=%s", display_name, suffix, dest.stat().st_size)
            await self._review_path(user_id, chat_id, dest, display_name)
            handled = True
        return handled

    async def _handle_text(self, user_id: int, chat_id: Optional[int], text: str) -> None:
        cmd = _command_name(text)
        low = " ".join((text or "").lower().replace("ё", "е").split()).strip("!,.?")
        if cmd in {"/start", "/help"} or low in _GREETINGS or low.startswith("привет"):
            await self._send(user_id=user_id or None, chat_id=chat_id, text=START_TEXT)
            return
        if cmd in {"/draft", "/web"}:
            await self._offer_web_draft(user_id, chat_id)
            return
        if cmd == "/review":
            self._waiting[user_id] = "review"
            await self._send(user_id=user_id, chat_id=chat_id, text=REVIEW_PROMPT)
            return
        waiting = self._waiting.get(user_id)
        if waiting == "review" or (waiting is None and len(text) >= 400):
            # длинный текст без команды — считаем договором
            dest = self.settings.data_dir / "uploads" / f"{user_id}_paste.txt"
            dest.write_text(text, encoding="utf-8")
            await self._review_path(user_id, chat_id, dest, "contract.txt")
            return
        if waiting == "draft":
            self._waiting.pop(user_id, None)
            await self._offer_web_draft(user_id, chat_id)
            return
        await self._send(
            user_id=user_id,
            chat_id=chat_id,
            text="Для проверки пришлите файл или текст договора. "
            "Чтобы составить договор — кнопка «Проект договора (веб)» или /draft.",
        )

    async def process_update(self, update: Dict[str, Any]) -> None:
        update_type = str(update.get("update_type") or update.get("type") or "").lower()
        message = update.get("message") or {}
        preview = self._message_text(message) if isinstance(message, dict) else ""
        logger.info(
            "update type=%s user_id=%s chat_id=%s text=%s",
            update_type or "-",
            self._sender_user_id(update, message) if isinstance(message, dict) else None,
            self._chat_id(message) if isinstance(message, dict) else None,
            (preview[:80] or "-"),
        )
        if update_type == "message_callback":
            callback = update.get("callback") or {}
            callback_id = str(callback.get("callback_id") or "")
            payload = str(callback.get("payload") or "").strip()
            user = callback.get("user") or update.get("user") or {}
            user_id = user.get("user_id") or user.get("id")
            message = update.get("message") or callback.get("message") or {}
            chat_id = self._chat_id(message) if isinstance(message, dict) else None
            if callback_id:
                await self._answer_callback(callback_id)
            if user_id is None:
                return
            user_id = int(user_id)
            if payload == "review":
                self._waiting[user_id] = "review"
                await self._send(user_id=user_id, chat_id=chat_id, text=REVIEW_PROMPT)
            elif payload == "draft":
                await self._offer_web_draft(user_id, chat_id)
            return
        if update_type == "bot_started":
            user = update.get("user") or {}
            uid = user.get("user_id") or user.get("id")
            if uid is not None:
                await self._send(user_id=int(uid), text=START_TEXT)
            return
        if update_type not in {"message_created", "message"} and "message" not in update:
            return
        if not message or self._sender_is_bot(message):
            if self._sender_is_bot(message):
                logger.info("skip bot echo")
            return
        user_id = self._sender_user_id(update, message)
        chat_id = self._chat_id(message)
        if user_id is None and chat_id is None:
            logger.warning("skip update without user_id/chat_id keys=%s", list(update)[:20])
            return
        files = await self._handle_files(int(user_id or 0), chat_id, self._attachments(message))
        text = self._message_text(message)
        if files:
            return
        if text:
            await self._handle_text(int(user_id or 0), chat_id, text)

    async def run(self) -> None:
        if not self.settings.max_enabled:
            raise RuntimeError("Задай MAX_BOT_TOKEN в .env")
        logger.info("ContractScout MAX polling api=%s", self.settings.max_api_base)
        marker: Optional[int] = None
        async with httpx.AsyncClient(verify=ssl_verify()) as client:
            while True:
                try:
                    params: Dict[str, Any] = {
                        "limit": 100,
                        "timeout": 30,
                        "types": "message_created,message_callback,bot_started",
                    }
                    if marker is not None:
                        params["marker"] = marker
                    resp = await client.get(
                        f"{self.settings.max_api_base}/updates",
                        params=params,
                        headers=_auth(self.settings),
                        timeout=45.0,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    marker = data.get("marker", marker)
                    updates = data.get("updates") or []
                    if updates:
                        logger.info("poll got %s updates marker=%s", len(updates), marker)
                    for update in updates:
                        await self.process_update(update)
                except httpx.HTTPError as exc:
                    logger.exception("MAX polling error: %s", exc)
                    await asyncio.sleep(3)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Loop error: %s", exc)
                    await asyncio.sleep(2)


def main() -> None:
    settings = load_settings()
    if settings.local_only:
        raise RuntimeError(
            "LOCAL_ONLY включён: MAX-бот отключён, потому что файлы шли бы через сеть MAX. "
            "Пользуйтесь локальным вебом: python -m contract_scout.web"
        )
    try:
        with httpx.Client(verify=ssl_verify(), timeout=20.0) as client:
            me = client.get(
                f"{settings.max_api_base}/me",
                headers=_auth(settings),
            ).json()
        logger.info(
            "MAX bot identity: name=%r username=@%s id=%s",
            me.get("name") or me.get("first_name"),
            me.get("username"),
            me.get("user_id"),
        )
    except Exception:
        logger.exception("Не удалось прочитать /me — проверьте MAX_BOT_TOKEN")
    asyncio.run(ContractMaxBot(settings).run())


if __name__ == "__main__":
    main()
