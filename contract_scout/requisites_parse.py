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

    labeled = _first(
        [
            r"(?i)(?:полное\s+)?(?:фирменное\s+)?наименование\s*[:–-]?\s*([^\n]+)",
            r"(?i)организация\s*[:–-]?\s*([^\n]+)",
            r"(?i)сторона\s*[:–-]?\s*([^\n]+)",
        ],
        cleaned,
    )
    if labeled and not _is_bankish_name(labeled):
        return labeled.strip(" .;")

    # полное «Общество с ограниченной ответственностью „…“»
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
        r"|ИП\s+[А-ЯЁ][^\n,]{3,80})",
        cleaned,
    ):
        cand = m.group(1).strip(" .;")
        score = 0
        if re.match(r"(?i)^ООО\b", cand):
            score += 3
        if re.match(r"(?i)^ИП\b", cand):
            score += 2
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
    person_type = str(data.get("person_type") or data.get("форма") or "ooo").strip().lower()
    if person_type in {"ооо", "ooo", "legal"}:
        person_type = "ooo"
    elif person_type in {"ип", "ip"}:
        person_type = "ip"
    inn = str(data.get("inn") or data.get("инн") or "").strip()
    kpp = str(data.get("kpp") or data.get("кпп") or "").strip()
    inn_kpp = str(data.get("inn_kpp") or "").strip()
    if not inn_kpp and inn:
        inn_kpp = f"{inn} / {kpp}" if kpp else inn
    return {
        "name": name,
        "person_type": person_type or "ooo",
        "form_label": str(data.get("form_label") or data.get("форма_подпись") or "").strip(),
        "inn_kpp": inn_kpp,
        "ogrn": str(data.get("ogrn") or data.get("огрн") or data.get("ogrnip") or "").strip(),
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
        or ("листа записи ЕГРИП" if person_type == "ip" else "Устава"),
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
    ogrn = _first([r"(?:ОГРНИП|ОГРН)\s*[:№]?\s*(\d{13,15})"], raw)
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
            r"Банк\s*[:–-]?\s*([^\n]+)",
            r"в\s+(ПАО|АО|ООО)\s+[«\"]?([^»\"\n,;]+)[»\"]?",
        ],
        raw,
    )
    if bank and re.match(r"^(ПАО|АО|ООО)$", bank, re.I):
        # второй вариант: группа 1 форма + 2 название — перечитаем
        m = re.search(r"в\s+((?:ПАО|АО|ООО)\s+[«\"]?[^»\"\n,;]+[»\"]?)", raw, re.I)
        bank = m.group(1).strip() if m else bank
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
    rep = _first(
        [
            r"(?:Генеральный\s+директор|Директор|Управляющий|в\s+лице)\s*[:–-]?\s*"
            r"([А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.|\s+[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+))",
            r"ФИО\s*[:–-]?\s*([А-ЯЁ][^\n]+)",
        ],
        raw,
    )
    basis = _first([r"(?:на\s+основании|действует\s+на\s+основании)\s*[:–-]?\s*([^\n.]+)"], raw)
    if person_type == "ip" and not basis:
        basis = "листа записи ЕГРИП"
    if person_type != "ip" and not basis:
        basis = "Устава"

    inn_kpp = f"{inn} / {kpp}" if inn and kpp else inn
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
