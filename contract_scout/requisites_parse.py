"""Разбор реквизитов стороны из загруженного файла (без внешних платных API)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def _first(patterns: list[str], text: str, flags: int = re.I | re.M) -> str:
    for pat in patterns:
        m = re.search(pat, text, flags)
        if m:
            return (m.group(1) if m.lastindex else m.group(0)).strip()
    return ""


def _extract_address(text: str) -> str:
    """Адрес целиком; если «д.» перенесено на следующую строку — склеиваем."""
    m = re.search(
        r"(?im)(?:юр\.?\s*адрес|юридический\s+адрес|почтовый\s+адрес|"
        r"адрес(?:\s+места\s+нахождения)?|место\s+нахождения)\s*[:–-]?\s*([^\n]+)",
        text or "",
    )
    if not m:
        # индекс / город без явной метки «адрес»
        m = re.search(
            r"(?im)^(\d{6}\s*,\s*г(?:ород)?\.?\s*[^\n]+)$",
            text or "",
        )
        if not m:
            return ""
    addr = m.group(1).strip(" ;,")
    # продолжение на следующей строке: «9А стр.5», «корп. 1», «оф. 12»
    after = (text or "")[m.end() :]
    cont = re.match(
        r"\s*\n\s*([0-9A-Za-zА-Яа-яЁё][^\n]{0,60})",
        after,
    )
    if cont:
        piece = cont.group(1).strip()
        if re.match(
            r"(?i)^(?:\d|[А-ЯA-Z]|стр\.?|строен|корп\.?|к\.|оф\.?|пом\.?|лит\.?)",
            piece,
        ) and not re.search(r"(?i)ИНН|ОГРН|КПП|БИК|банк|р/?с|тел|email|директор", piece):
            # обрезка на «д.» / «д. » — типичный перенос
            if re.search(r"(?i)(?:^|[,\s])(?:д|дом|стр|строен|корп|к|оф)\.?\s*$", addr) or len(addr) < 40:
                addr = f"{addr} {piece}".strip()
    return re.sub(r"\s+", " ", addr).strip(" ;,")


def _extract_phone(text: str) -> str:
    """Телефон только по метке; не путать с фрагментом р/с или ИНН."""
    labeled = _first(
        [
            r"(?i)(?:тел(?:ефон)?\.?|phone|моб(?:ильный)?\.?)\s*[:–-]?\s*"
            r"((?:\+7|8)[\s\-(]?\d{3}[\s\-)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})",
        ],
        text or "",
    )
    if labeled:
        return labeled
    # без метки — только явный +7 / 8(xxx)
    m = re.search(
        r"(?<!\d)(\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
        r"|8[\s\-]?\(\d{3}\)[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})(?!\d)",
        text or "",
    )
    return m.group(1).strip() if m else ""


def _genitive_post(post: str) -> str:
    text = (post or "").strip()
    if not text:
        return ""
    low = text.lower()
    mapping = {
        "генеральный директор": "Генерального директора",
        "директор": "Директора",
        "управляющий": "Управляющего",
        "президент": "Президента",
        "председатель": "Председателя",
    }
    return mapping.get(low, text)


def _mask_bank_blocks(text: str) -> str:
    """Убирает строки/фрагменты про банк, чтобы АО «АЛЬФА-БАНК» не стало наименованием стороны."""
    lines = []
    for line in (text or "").splitlines():
        if re.search(
            r"(?i)\bбанк\b|\bбик\b|корр?\.?\s*сч|к/\s*с|р/\s*с|расчётн\w*\s+сч|расчетн\w*\s+сч",
            line,
        ):
            lines.append("")
            continue
        lines.append(line)
    return "\n".join(lines)


def _is_bankish_name(name: str) -> bool:
    low = (name or "").lower().replace("ё", "е")
    return bool(re.search(r"банк|credit|bank", low))


def _find_org_line(text: str) -> str:
    """Ищет наименование стороны, игнорируя банк в реквизитах."""
    cleaned = _mask_bank_blocks(text)

    ip_labeled = _first(
        [
            r"(?is)индивидуальный\s+предприниматель\s*[:–-]?\s*([^\n]+)",
            r"(?is)индивидуальный\s+предприниматель\s*\n\s*([А-ЯЁ][^\n,]{3,80})",
        ],
        cleaned,
    )
    if ip_labeled and not _is_bankish_name(ip_labeled):
        return f"ИП {ip_labeled.strip(' .;')}"

    se_labeled = _first(
        [
            r"(?is)самозанят(?:ый|ая|ого|ой)?\s*[:–-]?\s*([А-ЯЁ][^\n,]{3,80})",
            r"(?is)плательщик\s+налога\s+на\s+профессиональный\s+доход\s*[:–-]?\s*([А-ЯЁ][^\n,]{3,80})",
            r"(?is)плательщик\s+налога\s+на\s+профессиональный\s+доход\s*\n\s*([А-ЯЁ][^\n,]{3,80})",
        ],
        cleaned,
    )
    if se_labeled and not _is_bankish_name(se_labeled):
        return f"Самозанятый {se_labeled.strip(' .;')}"

    labeled = _first(
        [
            r"(?i)(?:полное\s+)?(?:фирменное\s+)?наименование(?!\s+банка)\s*[:–-]?\s*([^\n]+)",
            r"(?i)организация\s*[:–-]?\s*([^\n]+)",
            r"(?i)сторона\s*[:–-]?\s*([^\n]+)",
        ],
        cleaned,
    )
    if labeled and not _is_bankish_name(labeled):
        low = labeled.strip().lower()
        # «Наименование организации» без значения на той же строке
        if low not in {"организации", "организации:", "банка", "компании", "стороны"}:
            return labeled.strip(" .;")

    # кавычки могут переноситься: "МЕЖДУНАРОДНАЯ ШКОЛА\nВОСТОЧНОЙ МЕДИЦИНЫ"
    quoted = re.search(
        r"(?is)(?:общество\s+с\s+ограниченной\s+ответственностью\s*)?[«\"“]([^»\"”]{5,160})[»\"”]",
        cleaned,
    )
    if quoted:
        inner = re.sub(r"\s+", " ", quoted.group(1)).strip()
        if inner and not _is_bankish_name(inner):
            return f'ООО «{inner}»'

    # полное «Общество с ограниченной ответственностью „…“» в одну строку
    full = re.search(
        r"(?i)(общество\s+с\s+ограниченной\s+ответственностью\s*[«\"“]?[^»\"”\n]+[»\"”]?)",
        cleaned,
    )
    if full:
        return full.group(1).strip()

    candidates: list[tuple[int, str]] = []
    for m in re.finditer(
        r"(?i)((?:ООО|АО|ПАО|НАО|ЗАО|ОАО)\s*[«\"“][^»\"”]+[»\"”]"
        r"|(?:ООО|АО|ПАО|НАО|ЗАО|ОАО)\s+[А-ЯЁA-Z][^\n,]{1,80}"
        r"|ИП\s+[А-ЯЁ][^\n,]{3,80}"
        r"|Самозанят(?:ый|ая)\s+[А-ЯЁ][^\n,]{3,80})",
        cleaned,
    ):
        cand = m.group(1).strip(" .;")
        score = 0
        if re.match(r"(?i)^ООО\b", cand):
            score += 3
        if re.match(r"(?i)^ИП\b", cand):
            score += 4
        if re.match(r"(?i)^Самозанят", cand):
            score += 5
        if re.search(r"(?i)индивидуальный\s+предприниматель", cand):
            score += 4
        if _is_bankish_name(cand):
            score -= 10
        # ближе к началу файла — выше
        score += max(0, 5 - m.start() // 80)
        candidates.append((score, cand))

    if candidates:
        candidates.sort(key=lambda x: (-x[0], x[1]))
        best = candidates[0]
        if best[0] > 0 or not _is_bankish_name(best[1]):
            return best[1]

    for line in cleaned.splitlines():
        s = line.strip()
        if len(s) < 2:
            continue
        if re.search(r"(?i)ИНН|ОГРН|КПП|адрес|email|тел|директор|основан", s):
            continue
        if _is_bankish_name(s):
            continue
        return s
    return ""


def normalize_person_type(value: str) -> str:
    key = (value or "").strip().lower().replace("ё", "е")
    mapping = {
        "ooo": "ooo",
        "ооо": "ooo",
        "legal": "legal",
        "ip": "ip",
        "ип": "ip",
        "selfemployed": "selfemployed",
        "самозанятый": "selfemployed",
        "individual": "individual",
        "физлицо": "individual",
        "физическое лицо": "individual",
        "custom": "custom",
    }
    return mapping.get(key, key or "ooo")


def infer_person_type(
    *,
    name: str = "",
    inn_kpp: str = "",
    ogrn: str = "",
    raw_text: str = "",
    explicit: str = "",
) -> str:
    """Определяет форму стороны: ИП / ООО / самозанятый / и т.д."""
    explicit_key = normalize_person_type(explicit)
    if explicit_key not in {"", "ooo", "legal"}:
        return explicit_key

    raw = (raw_text or "").lower().replace("ё", "е")
    up_name = (name or "").upper().replace("Ё", "Е")
    ogrn_digits = re.sub(r"\D", "", ogrn or "")

    if re.search(r"самозанят|налог(?:а|е)?\s+на\s+профессиональн\w*\s+доход|\bнпд\b", raw):
        return "selfemployed"
    if re.search(r"физическ\w*\s+лиц|\bгражданин\b", raw) and not re.search(
        r"\bогрн|\bип\b|индивидуальный\s+предприниматель|ооо",
        raw,
    ):
        # только если явно физлицо и нет признаков ИП/ООО
        if re.search(r"физическ\w*\s+лиц", raw):
            return "individual"

    if re.search(r"\bогрнип\b", raw) or len(ogrn_digits) == 15:
        return "ip"
    if re.search(r"индивидуальный\s+предприниматель", raw):
        return "ip"
    if up_name.startswith("ИП ") or re.match(r"(?i)^ип\b", name or ""):
        return "ip"

    inn_digits = re.sub(r"\D", "", inn_kpp or "")
    has_kpp = bool(re.search(r"\bкпп\b", raw)) or " / " in (inn_kpp or "")
    if len(inn_digits) == 12 and not has_kpp:
        return "ip"

    return explicit_key or "ooo"


def default_basis_for_type(person_type: str) -> str:
    key = normalize_person_type(person_type)
    if key == "ip":
        return "листа записи ЕГРИП"
    if key in {"selfemployed", "individual"}:
        return "паспорта гражданина РФ"
    return "Устава"


def _extract_ogrn(raw: str) -> str:
    return _first(
        [
            r"(?:ОГРНИП|ОГРН(?:ИП)?(?:\s*/\s*ОГРНИП)?)\s*[:№]?\s*(\d{13,15})",
            r"(?i)рег(?:истрационн\w*)?\s*номер\s*[:№]?\s*(\d{13,15})",
        ],
        raw or "",
    )


def _short_org_name(raw: str) -> tuple[str, str, str]:
    """Возвращает (name, person_type, form_label)."""
    text = (raw or "").strip()
    if not text:
        return "", "ooo", ""
    # Общество с ограниченной ответственностью «Вектор»
    full = re.match(
        r"(?i)^общество\s+с\s+ограниченной\s+ответственностью\s*[«\"“]?([^»\"”]+)[»\"”]?$",
        text,
    )
    if full:
        return full.group(1).strip(" «»\"'"), "ooo", ""
    ip_entrepreneur = re.match(
        r"(?i)^индивидуальный\s+предприниматель\s+(.+)$",
        text,
    )
    if ip_entrepreneur:
        return ip_entrepreneur.group(1).strip(" «»\"'"), "ip", ""
    se = re.match(
        r"(?i)^самозанят(?:ый|ая)\s+(.+)$",
        text,
    )
    if se:
        return se.group(1).strip(" «»\"'"), "selfemployed", ""
    ip = re.match(
        r"^ИП\s+(.+)$",
        text,
        re.I,
    )
    if ip:
        return ip.group(1).strip(" «»\"'"), "ip", ""
    m = re.match(
        r"^(ООО|АО|ПАО|НАО|ЗАО|ОАО)\s*[«\"“]?([^»\"”]+)[»\"”]?$",
        text,
        re.I,
    )
    if m:
        form = m.group(1).upper()
        name = m.group(2).strip(" «»\"'")
        if form == "ООО":
            return name, "ooo", ""
        return name, "custom", form
    bare = text.strip(" «»\"'")
    return bare, "ooo", ""


def _card_from_mapping(data: Dict[str, Any]) -> Dict[str, Any]:
    name = str(data.get("name") or data.get("наименование") or "").strip()
    person_type = normalize_person_type(str(data.get("person_type") or data.get("форма") or "ooo"))
    inn = str(data.get("inn") or data.get("инн") or "").strip()
    kpp = str(data.get("kpp") or data.get("кпп") or "").strip()
    inn_kpp = str(data.get("inn_kpp") or "").strip()
    if not inn_kpp and inn:
        inn_kpp = f"{inn} / {kpp}" if kpp else inn
    ogrn = str(data.get("ogrn") or data.get("огрн") or data.get("ogrnip") or data.get("огрнип") or "").strip()
    person_type = infer_person_type(
        name=name,
        inn_kpp=inn_kpp,
        ogrn=ogrn,
        raw_text=json.dumps(data, ensure_ascii=False),
        explicit=person_type,
    )
    return {
        "name": name,
        "person_type": person_type,
        "form_label": str(data.get("form_label") or data.get("форма_подпись") or "").strip(),
        "inn_kpp": inn_kpp,
        "ogrn": ogrn,
        "address": str(data.get("address") or data.get("адрес") or "").strip(),
        "phone": str(data.get("phone") or data.get("тел") or data.get("телефон") or "").strip(),
        "email": str(data.get("email") or "").strip(),
        "rs": str(data.get("rs") or data.get("р_с") or data.get("р/с") or "").strip(),
        "bank": str(data.get("bank") or data.get("банк") or "").strip(),
        "bik": str(data.get("bik") or data.get("бик") or "").strip(),
        "ks": str(data.get("ks") or data.get("к_с") or data.get("к/с") or "").strip(),
        "rep_title": str(data.get("rep_title") or data.get("должность") or "").strip(),
        "rep": str(data.get("rep") or data.get("фио") or data.get("директор") or "").strip(),
        "basis": str(data.get("basis") or data.get("основание") or "").strip()
        or default_basis_for_type(person_type),
        "source": "file",
    }


def parse_requisites_text(text: str) -> Dict[str, Any]:
    """Извлекает карточку стороны из текста реквизитов или JSON."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Файл пустой.")

    if raw.startswith("{") or raw.startswith("["):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Не удалось разобрать JSON с реквизитами.") from exc
        if isinstance(data, list):
            data = data[0] if data and isinstance(data[0], dict) else {}
        if not isinstance(data, dict):
            raise ValueError("JSON должен быть объектом с полями реквизитов.")
        card = _card_from_mapping(data)
        if not card.get("name") and not card.get("inn_kpp"):
            raise ValueError("В JSON нет названия или ИНН.")
        return card

    inn = _first([r"ИНН\s*[:№]?\s*(\d{10,12})", r"\b(\d{10}|\d{12})\b"], raw)
    kpp = _first([r"КПП\s*[:№]?\s*(\d{9})"], raw)
    ogrn = _extract_ogrn(raw)
    bik = _first([r"БИК\s*[:№]?\s*(\d{9})"], raw)
    rs = _first(
        [
            r"(?:р/?сч?ё?т|расчётн\w*\s+счёт|р/\s*с)\s*[:№]?\s*(\d{20})",
            r"\b(40\d{18})\b",
        ],
        raw,
    )
    ks = _first(
        [
            r"(?:кор(?:р)?\.?\s*счёт|к/?с)\s*[:№]?\s*(\d{20})",
            r"\b(30\d{18})\b",
        ],
        raw,
    )
    bank = _first(
        [
            # «Наименование банка АО …» / «Банк: …» — не резать слово «банка» посередине
            r"(?i)(?:наименование\s+)?банка?\b\s*[:–-]?\s*([^\n]+)",
            r"в\s+((?:ПАО|АО|ООО)\s+[«\"]?[^»\"\n,;]+[»\"]?)",
        ],
        raw,
    )
    if bank:
        bank = re.sub(r"(?i)^наименование\s+", "", bank).strip(" ,;")
    address = _extract_address(raw)
    email = _first([r"([\w.+-]+@[\w-]+\.[\w.-]+)"], raw)
    phone = _extract_phone(raw)

    org_line = _find_org_line(raw)
    name, person_type, form_label = _short_org_name(org_line)

    post = _first(
        [
            r"(Генеральный\s+директор|Директор|Управляющий|Президент|Председатель)\s*[:–-]?",
        ],
        raw,
    )
    # только текущая строка: иначе «Подключена к Контуру» станет «отчеством»
    rep = _first(
        [
            r"(?im)(?:Генеральный\s+директор|Директор|Управляющий|Президент|Председатель|в\s+лице)"
            r"\s*[:–-]?\s*([А-ЯЁ][^\n]+)",
            r"(?im)ФИО\s*[:–-]?\s*([А-ЯЁ][^\n]+)",
        ],
        raw,
    )
    if rep:
        rep = re.split(
            r"(?i)\b(?:подключен\w*|оператор\s+эдо|идентификатор|инн|огрн|кпп)\b",
            rep,
            maxsplit=1,
        )[0]
        rep = re.sub(r"\s+", " ", rep).strip(" .,;:")
    basis = _first([r"(?:на\s+основании|действует\s+на\s+основании)\s*[:–-]?\s*([^\n.]+)"], raw)
    inn_kpp = f"{inn} / {kpp}" if inn and kpp else inn
    person_type = infer_person_type(
        name=name,
        inn_kpp=inn_kpp,
        ogrn=ogrn,
        raw_text=raw,
        explicit=person_type,
    )
    if not basis:
        basis = default_basis_for_type(person_type)
    elif person_type in {"selfemployed", "individual"} and basis.strip() in {"Устава", "листа записи ЕГРИП"}:
        basis = default_basis_for_type(person_type)
    elif person_type == "ip" and basis.strip() == "Устава":
        basis = default_basis_for_type(person_type)

    if not name and not inn:
        raise ValueError("Не удалось найти название или ИНН в файле реквизитов.")

    return {
        "name": name or "________________",
        "person_type": person_type,
        "form_label": form_label,
        "inn_kpp": inn_kpp,
        "ogrn": ogrn,
        "address": address,
        "phone": phone,
        "email": email,
        "rs": rs,
        "bank": bank.strip(" ,;") if bank else "",
        "bik": bik,
        "ks": ks,
        "rep_title": _genitive_post(post),
        "rep": rep,
        "basis": basis,
        "source": "file",
        "value": org_line or name,
    }


_ROLE_TO_PREFIX = {
    "заказчик": "customer",
    "исполнитель": "contractor",
    "продавец": "customer",
    "покупатель": "contractor",
    "поставщик": "customer",
    "арендодатель": "customer",
    "арендатор": "contractor",
    "займодавец": "customer",
    "заёмщик": "contractor",
    "заемщик": "contractor",
    "лицензиар": "customer",
    "лицензиат": "contractor",
    "принципал": "customer",
    "агент": "contractor",
    "раскрывающая сторона": "customer",
    "получающая сторона": "contractor",
}


def _form_key_from_label(label: str) -> str:
    low = (label or "").lower().replace("ё", "е")
    if low in {"ип", "индивидуальный предприниматель"}:
        return "ip"
    if low in {"ооо", "общество с ограниченной ответственностью"}:
        return "ooo"
    if "самозанят" in low:
        return "selfemployed"
    if "физ" in low:
        return "individual"
    return ""


def _parse_contract_party_block(block: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    form_label = _first([r"(?im)^\s*Форма:\s*(.+)$"], block)
    if form_label:
        form_key = _form_key_from_label(form_label)
        if form_key:
            out["person_type"] = form_key
    name = _first(
        [
            r"(?im)^\s*ФИО\s*/\s*наименование\s+ИП:\s*(.+)$",
            r"(?im)^\s*Наименование\s*/\s*ФИО:\s*(.+)$",
            r"(?im)^\s*Наименование:\s*(.+)$",
            r"(?im)^\s*ФИО:\s*(.+)$",
        ],
        block,
    )
    if name:
        out["name"] = name.strip()
    inn = _first(
        [
            r"(?im)^\s*ИНН/КПП:\s*(.+)$",
            r"(?im)^\s*ИНН:\s*(.+)$",
        ],
        block,
    )
    if inn:
        out["inn_kpp"] = inn.strip()
    ogrn = _first(
        [
            r"(?im)^\s*ОГРНИП:\s*(.+)$",
            r"(?im)^\s*ОГРН:\s*(.+)$",
        ],
        block,
    )
    if ogrn:
        out["ogrn"] = re.sub(r"\D", "", ogrn) or ogrn.strip()
    address = _first(
        [
            r"(?im)^\s*Юр\.\s*адрес:\s*(.+)$",
            r"(?im)^\s*Адрес:\s*(.+)$",
        ],
        block,
    )
    if address:
        out["address"] = address.strip()
    rep_title = _first([r"(?im)^\s*В\s+лице:\s*(.+)$"], block)
    if rep_title:
        parts = rep_title.strip().split(None, 1)
        if parts:
            out["rep_title"] = parts[0]
            if len(parts) > 1:
                out["rep"] = parts[1].strip()
    basis = _first([r"(?im)^\s*(?:На\s+основании|Действует\s+лично\s+на\s+основании):\s*(.+)$"], block)
    if basis:
        out["basis"] = basis.strip()
    phone = _first([r"(?im)^\s*Тел\.:\s*(.+)$"], block)
    if phone:
        out["phone"] = phone.strip()
    email = _first([r"(?im)^\s*Email:\s*(.+)$"], block)
    if email:
        out["email"] = email.strip()
    rs = _first([r"(?im)^\s*Р/с:\s*(.+)$"], block)
    if rs:
        out["rs"] = rs.strip()
    bank = _first([r"(?im)^\s*Банк:\s*(.+)$"], block)
    if bank:
        out["bank"] = bank.strip()
    bik = _first([r"(?im)^\s*БИК:\s*(.+)$"], block)
    if bik:
        out["bik"] = bik.strip()
    ks = _first([r"(?im)^\s*К/с:\s*(.+)$"], block)
    if ks:
        out["ks"] = ks.strip()
    if out.get("name") or out.get("inn_kpp") or out.get("ogrn"):
        out["person_type"] = infer_person_type(
            name=out.get("name", ""),
            inn_kpp=out.get("inn_kpp", ""),
            ogrn=out.get("ogrn", ""),
            raw_text=block,
            explicit=out.get("person_type", ""),
        )
    return out


def extract_parties_from_contract(text: str) -> Dict[str, str]:
    """Локально извлекает реквизиты сторон из текста договора (без ИИ)."""
    raw = (text or "").strip()
    if len(raw) < 80:
        return {}
    section = raw
    req = re.search(r"(?is)(?:##\s*)?(?:\d+\.\s*)?реквизиты\s+и\s+подписи\s+сторон(.+)$", raw)
    if req:
        section = req.group(1)
    out: Dict[str, str] = {}
    for role, body in re.findall(
        r"(?is)###\s*([^\n#]+?)\s*\n(.+?)(?=###|\Z)",
        section,
    ):
        prefix = _ROLE_TO_PREFIX.get(role.strip().lower().replace("ё", "е"))
        if not prefix:
            continue
        card = _parse_contract_party_block(body)
        for key, value in card.items():
            if value:
                out[f"{prefix}_{key}"] = value
    return out
