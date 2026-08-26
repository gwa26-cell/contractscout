"""Настройки ContractScout из .env."""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    def load_dotenv(*_a, **_k):  # pragma: no cover
        return False

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

_RU_CA = ROOT / "certs" / "russiantrustedca.pem"
# совместимость с учебным MaxVkContentBot, если certs скопировали рядом
_SIBLING_CA = ROOT.parent / "MaxVkContentBot" / "certs" / "russiantrustedca.pem"


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is not None and str(value).strip():
        return str(value).strip()
    return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def ssl_verify():
    try:
        import certifi

        cafile = certifi.where()
    except ImportError:
        cafile = None
    ctx = ssl.create_default_context(cafile=cafile)
    for ca in (_RU_CA, _SIBLING_CA):
        if ca.is_file():
            ctx.load_verify_locations(cafile=str(ca))
            break
    return ctx


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_base_url: str
    chat_model: str
    embedding_provider: str
    embedding_model: str
    openai_embedding_model: str
    max_bot_token: str
    max_api_base: str
    web_host: str
    web_port: int
    secret_key: str
    pinecone_api_key: str
    pinecone_index_name: str
    pinecone_namespace: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    notify_from: str
    notify_to: str
    data_dir: Path
    match_count: int
    log_level: str
    local_only: bool
    redact_requisites: bool
    public_base_url: str
    trust_proxy: bool
    allowed_hosts: str
    yookassa_shop_id: str
    yookassa_secret_key: str
    yookassa_amount: str
    yookassa_credits: int
    yookassa_vat_code: int
    paywall_enabled: bool
    operator_name: str
    operator_inn: str
    operator_ogrn: str
    operator_email: str
    operator_address: str
    yookassa_require_receipt: bool

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def max_enabled(self) -> bool:
        return bool(self.max_bot_token)

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.notify_to) and not self.local_only

    @property
    def pinecone_enabled(self) -> bool:
        return bool(self.pinecone_api_key)

    @property
    def yookassa_enabled(self) -> bool:
        return bool(self.yookassa_shop_id and self.yookassa_secret_key)

    @property
    def cookie_secure(self) -> bool:
        return (self.public_base_url or "").lower().startswith("https://")


def load_settings() -> Settings:
    openai_key = _env("OPENAI_API_KEY")
    deepseek_key = _env("DEEPSEEK_API_KEY")
    openai_base = _env("OPENAI_BASE_URL").rstrip("/")
    deepseek_base = (_env("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")

    if openai_key:
        api_key = openai_key
        base_url = openai_base or "https://api.openai.com/v1"
        chat_model = _env("CHAT_MODEL") or _env("OPENAI_MODEL") or "gpt-4o-mini"
    elif deepseek_key:
        api_key = deepseek_key
        base_url = deepseek_base
        chat_model = _env("CHAT_MODEL") or _env("DEEPSEEK_MODEL") or "deepseek-chat"
    else:
        api_key = ""
        base_url = deepseek_base
        chat_model = _env("CHAT_MODEL") or "deepseek-chat"

    data_dir = Path(_env("DATA_DIR") or str(ROOT / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "uploads").mkdir(exist_ok=True)
    (data_dir / "exports").mkdir(exist_ok=True)

    local_only = _env_bool("LOCAL_ONLY", True)
    redact_requisites = _env_bool("REDACT_REQUISITES", True)
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_BASE_URL"] = base_url
    if local_only:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        embedding_provider = "hash"
        smtp_host = ""
        notify_to = ""
        # бот можно запускать и при LOCAL_ONLY=1, если токен задан;
        # ссылка на веб должна быть публичной (PUBLIC_BASE_URL), не localhost
        max_token = _env("MAX_BOT_TOKEN") or _env("BOT_TOKEN")
    else:
        embedding_provider = (_env("EMBEDDING_PROVIDER") or "local").lower().strip()
        smtp_host = _env("SMTP_HOST")
        notify_to = _env("NOTIFY_TO")
        max_token = _env("MAX_BOT_TOKEN") or _env("BOT_TOKEN")
    # Pinecone — поиск по обезличенным чанкам; картотека проектов всегда локальная.
    pinecone_key = _env("PINECONE_API_KEY")
    public_base = (_env("PUBLIC_BASE_URL") or "").rstrip("/")
    yookassa_shop = _env("YOOKASSA_SHOP_ID")
    yookassa_secret = _env("YOOKASSA_SECRET_KEY")
    want_paywall = _env_bool("PAYWALL", False)
    paywall = want_paywall and bool(yookassa_shop and yookassa_secret)

    return Settings(
        openai_api_key=api_key,
        openai_base_url=base_url,
        chat_model=chat_model,
        embedding_provider=embedding_provider,
        embedding_model=_env("EMBEDDING_MODEL")
        or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        openai_embedding_model=_env("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small",
        max_bot_token=max_token,
        max_api_base=(_env("MAX_API_BASE") or "https://platform-api2.max.ru").rstrip("/"),
        web_host=_env("WEB_HOST") or "0.0.0.0",
        web_port=int(_env("PORT") or _env("WEB_PORT") or "8080"),
        secret_key=_env("SECRET_KEY") or "dev-secret",
        pinecone_api_key=pinecone_key,
        pinecone_index_name=_env("PINECONE_INDEX_NAME") or "contract-scout",
        pinecone_namespace=_env("PINECONE_NAMESPACE") or "contracts",
        smtp_host=smtp_host,
        smtp_port=int(_env("SMTP_PORT") or "587"),
        smtp_user=_env("SMTP_USER"),
        smtp_password=_env("SMTP_PASSWORD"),
        notify_from=_env("NOTIFY_FROM"),
        notify_to=notify_to,
        data_dir=data_dir,
        match_count=int(_env("MATCH_COUNT") or "8"),
        log_level=_env("LOG_LEVEL") or "INFO",
        local_only=local_only,
        redact_requisites=redact_requisites,
        public_base_url=public_base,
        trust_proxy=_env_bool("TRUST_PROXY", bool(public_base)),
        allowed_hosts=_env("ALLOWED_HOSTS") or "*",
        yookassa_shop_id=yookassa_shop,
        yookassa_secret_key=yookassa_secret,
        yookassa_amount=_env("YOOKASSA_AMOUNT") or "490.00",
        yookassa_credits=int(_env("YOOKASSA_CREDITS") or "5"),
        yookassa_vat_code=int(_env("YOOKASSA_VAT_CODE") or "1"),
        paywall_enabled=paywall,
        operator_name=_env("OPERATOR_NAME") or "Оператор сервиса ContractScout",
        operator_inn=_env("OPERATOR_INN") or "укажите ИНН",
        operator_ogrn=_env("OPERATOR_OGRN") or "укажите ОГРН/ОГРНИП",
        operator_email=_env("OPERATOR_EMAIL") or "privacy@example.com",
        operator_address=_env("OPERATOR_ADDRESS") or "укажите адрес",
        yookassa_require_receipt=_env_bool("YOOKASSA_REQUIRE_RECEIPT", True),
    )
