"""Сборка сервиса: каталог рисков в RAG, ingest, архив, review, draft."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from contract_scout.billing import BillingLedger
from contract_scout.config import Settings, load_settings
from contract_scout.draft import DraftBrief, DraftPipeline, brief_from_form, markdown_to_docx
from contract_scout.embeddings import EmbeddingBackend
from contract_scout.ingest import ingest_path
from contract_scout.knowledge import knowledge_rows
from contract_scout.llm import ChatLLM
from contract_scout.parties import PartyBook, card_from_brief
from contract_scout.payments import YooKassaGateway
from contract_scout.pinecone_archive import PineconeArchive, cosine
from contract_scout.projects import ProjectArchive, extract_contract_title, public_summary
from contract_scout.redact import redact_requisites
from contract_scout.requisites_parse import parse_requisites_text
from contract_scout.review import ReviewPipeline, contract_text_from_rows
from contract_scout.store import VectorStore
from contract_scout.types import kind_label, normalize_kind

logger = logging.getLogger("contract_scout.service")

# Индекс риска 0–100: чем ниже, тем лучше. Ниже порога — кандидат в «удачный пример».
EXAMPLE_MAX_RISK = 40


def _full_report_text(report: Dict[str, Any]) -> str:
    lines = [
        f"Файл: {report.get('filename')}",
        f"Тип: {report.get('contract_kind_label') or report.get('contract_kind')}",
        f"Индекс риска: {report.get('overall_score')}/100 — {report.get('verdict')}",
        f"Режим: {report.get('mode')}",
        "",
        str(report.get("summary") or ""),
        "",
        "Узкие места:",
    ]
    for item in report.get("bottlenecks") or []:
        ref = item.get("clause_ref")
        title = item.get("title") or ""
        if ref:
            title = f"{title} ({ref})"
        lines.append(f"• [{item.get('severity')}] {title}")
        if item.get("quote"):
            lines.append(f"  «{item.get('quote')}»")
        if item.get("why"):
            lines.append(f"  Почему: {item.get('why')}")
        if item.get("fix"):
            lines.append(f"  Как чинить: {item.get('fix')}")
    missing = report.get("missing_clauses") or []
    if missing:
        lines.append("\nПробелы:")
        for m in missing:
            title = m.get("title") if isinstance(m, dict) else str(m)
            why = m.get("why") if isinstance(m, dict) else ""
            lines.append(f"• {title}" + (f" — {why}" if why else ""))
    script = report.get("negotiate_script") or []
    if script:
        lines.append("\nСкрипт переговоров:")
        for s in script:
            lines.append(f"• {s}")
    lines.append("\n" + str(report.get("disclaimer") or ""))
    return "\n".join(lines)


class ContractScout:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embedder = EmbeddingBackend(settings)
        self.store = VectorStore(settings, self.embedder)
        self.llm = ChatLLM(settings)
        self.reviewer = ReviewPipeline(self.store, self.llm)
        self.drafter = DraftPipeline(self.llm)
        self.parties = PartyBook(settings.data_dir / "parties.json")
        self.archive = ProjectArchive(settings.data_dir / "projects")
        self.pinecone = PineconeArchive(settings, self.embedder)
        self.billing = BillingLedger(settings.data_dir / "billing.json")
        self.payments = YooKassaGateway(settings, self.billing)
        self._ensure_knowledge()

    def _ensure_knowledge(self) -> None:
        ping = self.store.ping()
        count = self.store.replace_namespace("knowledge", knowledge_rows())
        logger.info("knowledge indexed=%s store=%s", count, ping)

    def _index_project(self, project_id: str, filename: str, rows: List[Dict[str, Any]]) -> bool:
        ns = f"project:{project_id}"
        self.store.replace_namespace(ns, rows)
        chunks = [row.get("content") or "" for row in rows]
        return self.pinecone.upsert_chunks(project_id, filename, chunks)

    @staticmethod
    def _risk_score(report: Optional[Dict[str, Any]]) -> int:
        if not isinstance(report, dict):
            return 100
        try:
            return int(report.get("overall_score") if report.get("overall_score") is not None else 100)
        except (TypeError, ValueError):
            return 100

    @classmethod
    def _is_good_example(cls, report: Optional[Dict[str, Any]]) -> bool:
        score = cls._risk_score(report)
        verdict = str((report or {}).get("verdict") or "").lower()
        return score <= EXAMPLE_MAX_RISK or "низк" in verdict

    def _chunks_for(self, text: str, filename: str = "") -> List[str]:
        rows = []
        try:
            # переиспользуем локальный чанкер через ingest chunk_text
            from contract_scout.ingest import chunk_text

            rows = chunk_text(text or "")
        except Exception:
            rows = [(text or "")[:4000]]
        if not rows and filename:
            rows = [filename]
        return rows

    def _local_similar(
        self,
        text: str,
        *,
        top_k: int = 6,
        examples_only: bool = False,
        exclude_project_id: str = "",
    ) -> List[Dict[str, Any]]:
        q, _ = redact_requisites((text or "")[:4000])
        if not (q or "").strip():
            return []
        q_emb = self.embedder.embed_query(q)
        hits: List[Dict[str, Any]] = []
        for row in self.archive.list():
            pid = str(row.get("id") or "")
            if not pid or pid == exclude_project_id:
                continue
            if examples_only and not row.get("is_example"):
                continue
            other = self.archive.read_text(pid) or str(row.get("preview") or row.get("title") or "")
            other_safe, _ = redact_requisites(other[:4000])
            score = cosine(q_emb, self.embedder.embed_query(other_safe or other[:4000]))
            report = row.get("report") if isinstance(row.get("report"), dict) else {}
            hits.append(
                {
                    "project_id": pid,
                    "filename": row.get("filename"),
                    "title": row.get("title") or row.get("filename"),
                    "score": score,
                    "snippet": str(row.get("preview") or "")[:240],
                    "role": "example" if row.get("is_example") else str(row.get("status") or "review"),
                    "is_example": bool(row.get("is_example")),
                    "risk_score": self._risk_score(report),
                    "contract_kind": row.get("contract_kind"),
                }
            )
        hits.sort(key=lambda h: float(h.get("score") or 0), reverse=True)
        return hits[:top_k]

    def find_similar(
        self,
        text: str,
        *,
        top_k: int = 6,
        examples_only: bool = False,
        exclude_project_id: str = "",
    ) -> List[Dict[str, Any]]:
        role = "example" if examples_only else None
        pine = self.pinecone.find_similar(
            text, top_k=top_k, role=role, exclude_project_id=exclude_project_id
        )
        if pine:
            return pine
        return self._local_similar(
            text, top_k=top_k, examples_only=examples_only, exclude_project_id=exclude_project_id
        )

    def _upsert_indexed(
        self,
        rec: Dict[str, Any],
        *,
        role: str,
        is_example: bool,
        risk_score: Optional[int] = None,
    ) -> bool:
        pid = str(rec.get("id") or "")
        text = rec.get("text") or self.archive.read_text(pid)
        title = str(rec.get("title") or extract_contract_title(text) or rec.get("filename") or "")
        chunks = self._chunks_for(text, str(rec.get("filename") or ""))
        ok = self.pinecone.upsert_document(
            pid,
            filename=str(rec.get("filename") or ""),
            title=title,
            contract_kind=str(rec.get("contract_kind") or "auto"),
            chunks=chunks,
            role=role,
            risk_score=risk_score,
            is_example=is_example,
        )
        return ok

    def _sync_after_review(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        """Индекс в Pinecone + политика примеров: сохранить / обновить / отклонить дубликат."""
        pid = str(rec.get("id") or "")
        text = rec.get("text") or self.archive.read_text(pid)
        report = rec.get("report") if isinstance(rec.get("report"), dict) else {}
        risk = self._risk_score(report)
        thr = self.pinecone.similar_threshold
        similar = self.find_similar(text, top_k=5, exclude_project_id=pid)
        close = [h for h in similar if float(h.get("score") or 0) >= thr]

        action = "indexed"
        note = "Договор проиндексирован для поиска."
        is_example = False

        if self._is_good_example(report):
            example_hits = [h for h in close if h.get("is_example") or h.get("role") == "example"]
            if example_hits:
                best = max(example_hits, key=lambda h: float(h.get("score") or 0))
                old_risk = best.get("risk_score")
                try:
                    old_risk_i = int(old_risk) if old_risk is not None and int(old_risk) >= 0 else 100
                except (TypeError, ValueError):
                    old_risk_i = 100
                if risk < old_risk_i:
                    # новый лучше — заменяем старый пример
                    old_id = str(best.get("project_id") or "")
                    if old_id:
                        self.pinecone.delete_project(old_id)
                        self.archive.update(old_id, is_example=False, example_replaced_by=pid)
                    is_example = True
                    action = "example_updated"
                    note = (
                        f"Похожий пример заменён более удачным (риск {risk} < {old_risk_i})."
                    )
                else:
                    action = "example_skipped"
                    note = (
                        f"Похожий удачный пример уже есть (сходство {float(best.get('score') or 0):.2f}, "
                        f"риск {old_risk_i}). Новый не сохранён как пример."
                    )
                    is_example = False
                    self.archive.update(
                        pid,
                        is_example=False,
                        similar_to=best.get("project_id"),
                        pinecone_action=action,
                        example_synced=True,
                    )
                    # всё равно индексируем как review
                    in_pc = self._upsert_indexed(rec, role="review", is_example=False, risk_score=risk)
                    self.archive.update(pid, in_pinecone=in_pc, pinecone_action=action, example_synced=True)
                    return {
                        "action": action,
                        "note": note,
                        "similar": close[:3],
                        "is_example": False,
                        "in_pinecone": in_pc,
                    }
            else:
                is_example = True
                action = "example_saved"
                note = f"Договор с низким риском ({risk}) сохранён как пример шаблона."

        role = "example" if is_example else "review"
        in_pc = self._upsert_indexed(rec, role=role, is_example=is_example, risk_score=risk)
        if not in_pc and is_example:
            # Pinecone выключен — пример всё равно локальный
            note = note + " (локально; Pinecone недоступен)."
        self.archive.update(
            pid,
            in_pinecone=in_pc,
            is_example=is_example,
            pinecone_action=action,
            example_synced=True,
            status=rec.get("status") or "ai",
        )
        return {
            "action": action,
            "note": note,
            "similar": close[:3],
            "is_example": is_example,
            "in_pinecone": in_pc,
        }

    def ingest_to_archive(
        self, path: Path, *, filename: str, kind: str = "auto"
    ) -> Dict[str, Any]:
        """Сохранить договор в локальный архив. ИИ не вызывается; в индекс — сразу."""
        rows = ingest_path(path, filename=filename, local_only=self.settings.local_only)
        full_text = contract_text_from_rows(rows)
        resolved = normalize_kind(kind, full_text)
        rec = self.archive.add(
            kind="contract",
            filename=filename,
            text=full_text,
            contract_kind=resolved,
        )
        report = self.reviewer.review(
            user_ns=f"project:{rec['id']}",
            filename=filename,
            full_text=full_text,
            kind=resolved,
            use_llm=False,
        )
        # предварительная индексация как review
        in_pc = self.pinecone.upsert_document(
            str(rec["id"]),
            filename=filename,
            title=str(rec.get("title") or filename),
            contract_kind=resolved,
            chunks=[r.get("content") or "" for r in rows],
            role="review",
            risk_score=self._risk_score(report),
            is_example=False,
        )
        # локальный vector store для RAG review
        self.store.replace_namespace(f"project:{rec['id']}", rows)
        similar = self.find_similar(full_text, top_k=3, exclude_project_id=str(rec["id"]))
        thr = self.pinecone.similar_threshold
        close = [h for h in similar if float(h.get("score") or 0) >= thr]
        rec = self.archive.update(
            rec["id"],
            in_pinecone=in_pc,
            status="stored",
            contract_kind=resolved,
            report=report,
            similar_preview=close[:3],
        ) or rec
        rec["similar"] = close[:3]
        return rec

    def run_ai_review(self, project_id: str) -> Dict[str, Any]:
        rec = self.archive.get(project_id)
        if rec is None:
            raise KeyError(project_id)
        filename = str(rec.get("filename") or "contract.txt")
        full_text = rec.get("text") or ""
        kind = str(rec.get("contract_kind") or "auto")
        report = self.reviewer.review(
            user_ns=f"project:{project_id}",
            filename=filename,
            full_text=full_text,
            kind=kind,
            use_llm=True,
        )
        report["privacy"] = {
            "local_only": self.settings.local_only,
            "sent_to_llm": bool(self.settings.llm_enabled),
            "requisites_redacted": int(report.get("requisites_redacted") or 0),
        }
        updated = self.archive.update(project_id, status="ai", report=report) or rec
        updated["text"] = full_text
        sync = self._sync_after_review(updated)
        report["library"] = sync
        updated = self.archive.update(project_id, report=report) or updated
        if self.settings.smtp_enabled:
            try:
                from contract_scout.notify import notify_review

                notify_review(
                    self.settings,
                    filename=filename,
                    verdict=str(report.get("verdict") or ""),
                    score=int(report.get("overall_score") or 0),
                    summary=str(report.get("summary") or ""),
                )
            except Exception:
                logger.exception("notify failed")
        return updated

    def ingest_and_review(
        self, path: Path, *, user_id: str, filename: str, kind: str = "auto"
    ) -> Dict[str, Any]:
        """Бот / одношаговый сценарий: архив + сразу ИИ, если ключ есть."""
        rec = self.ingest_to_archive(path, filename=filename, kind=kind)
        if self.settings.llm_enabled:
            rec = self.run_ai_review(str(rec["id"]))
        report = rec.get("report") if isinstance(rec.get("report"), dict) else {}
        report = dict(report)
        report["project_id"] = rec.get("id")
        report["privacy"] = {
            "local_only": self.settings.local_only,
            "sent_to_llm": rec.get("status") == "ai" and self.settings.llm_enabled,
            "requisites_redacted": int(report.get("requisites_redacted") or 0),
        }
        return report

    def list_projects(self) -> List[Dict[str, Any]]:
        return [public_summary(row) for row in self.archive.list()]

    def search_party_cards(self, query: str, *, limit: int = 8) -> Dict[str, Any]:
        """Локальная книга сохранённых сторон."""
        q = (query or "").strip()
        local = self.parties.search(q, limit=limit)
        for row in local:
            row.setdefault("source", "local")
        return {"parties": local}

    def parse_party_file(self, path: Path, *, filename: str = "") -> Dict[str, Any]:
        """Прочитать TXT/DOCX/PDF/JSON с реквизитами и вернуть карточку стороны."""
        suffix = Path(filename or path.name).suffix.lower()
        if suffix == ".json":
            text = path.read_text(encoding="utf-8")
        else:
            rows = ingest_path(path, filename=filename or path.name, local_only=True)
            from contract_scout.review import contract_text_from_rows

            text = contract_text_from_rows(rows)
        card = parse_requisites_text(text)
        self.parties.upsert(card)
        return card

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        rec = self.archive.get(project_id)
        if rec is None:
            return None
        out = public_summary(rec)
        out["text"] = rec.get("text") or ""
        out["report"] = rec.get("report")
        out["contract_kind_label"] = kind_label(str(rec.get("contract_kind") or "auto"))
        return out

    def search_projects(self, query: str) -> Dict[str, Any]:
        q = (query or "").strip().lower().replace("ё", "е")
        if not q:
            return {"projects": [], "pinecone": [], "pinecone_enabled": self.pinecone.enabled}

        def norm(s: str) -> str:
            return (s or "").lower().replace("ё", "е")

        def tokens(s: str) -> list[str]:
            return re.findall(r"[a-zа-я0-9]+", norm(s))

        def soft_match(needle: str, hay: str) -> bool:
            """Подстрока или совпадение слов с общим началом (услуги ↔ услуг)."""
            h = norm(hay)
            if not needle or not h:
                return False
            if needle in h:
                return True
            n_words = tokens(needle)
            h_words = tokens(h)
            if not n_words:
                return False
            for nw in n_words:
                if len(nw) < 2:
                    continue
                if not any(
                    hw.startswith(nw) or nw.startswith(hw)
                    for hw in h_words
                    if len(hw) >= 2
                ):
                    return False
            return True

        local = []
        for row in self.list_projects():
            title = str(row.get("title") or "")
            kind = str(row.get("contract_kind") or "")
            label = kind_label(kind)
            preview = str(row.get("preview") or "")
            filename = str(row.get("filename") or "")
            # приоритет: название договора и тип; файл — только запасной источник
            blob_title = f"{title} {label} {preview}"
            if soft_match(q, blob_title) or soft_match(q, filename):
                scored = 0 if soft_match(q, title) else 1 if soft_match(q, label) else 2
                local.append((scored, row))
        local.sort(key=lambda item: (item[0], str(item[1].get("title") or "")))
        projects = [row for _, row in local]
        pine = self.pinecone.search(query, top_k=8) if len(q) >= 3 else []
        return {"projects": projects, "pinecone": pine, "pinecone_enabled": self.pinecone.enabled}

    def list_examples(self, query: str = "") -> Dict[str, Any]:
        """Удачные примеры для шаблонов: локальные флаги + Pinecone."""
        self._backfill_examples()
        q = (query or "").strip().lower().replace("ё", "е")
        local: List[Dict[str, Any]] = []
        for row in self.list_projects():
            if not row.get("is_example"):
                continue
            if q:
                blob = " ".join(
                    str(row.get(k) or "")
                    for k in ("title", "preview", "filename", "contract_kind")
                ).lower().replace("ё", "е")
                label = kind_label(str(row.get("contract_kind") or "")).lower().replace("ё", "е")
                if q not in blob and q not in label:
                    words = [w for w in re.findall(r"[a-zа-я0-9]+", q) if len(w) >= 3]
                    if not words or not any(w in blob or w in label for w in words):
                        continue
            local.append(row)
        pine = (
            self.pinecone.search(query or "договор услуги", top_k=8, examples_only=True)
            if self.pinecone.enabled
            else []
        )
        if not local and pine:
            for hit in pine:
                pid = str(hit.get("project_id") or "")
                got = self.get_project(pid)
                if got:
                    local.append({k: got[k] for k in got if k != "text" and k != "report"})
        return {
            "examples": local,
            "pinecone": pine,
            "pinecone_enabled": self.pinecone.enabled,
        }

    def _backfill_examples(self) -> None:
        """Разово пометить уже проверенные договоры с низким риском как примеры."""
        for row in self.archive.list():
            if row.get("example_synced") or row.get("is_example"):
                continue
            if row.get("status") not in {"ai", "stored"}:
                continue
            report = row.get("report") if isinstance(row.get("report"), dict) else {}
            if not report or not self._is_good_example(report):
                if report:
                    self.archive.update(str(row.get("id")), example_synced=True)
                continue
            pid = str(row.get("id") or "")
            rec = self.archive.get(pid)
            if not rec:
                continue
            sync = self._sync_after_review(rec)
            self.archive.update(pid, example_synced=True)
            logger.info("backfill example id=%s action=%s", pid, sync.get("action"))

    def draft(self, form: Dict[str, Any] | DraftBrief) -> str:
        brief = form if isinstance(form, DraftBrief) else brief_from_form(form)
        examples = self._examples_for_draft(brief)
        markdown = self.drafter.generate(brief, examples=examples)
        self.parties.upsert(card_from_brief(brief, "customer"))
        self.parties.upsert(card_from_brief(brief, "contractor"))
        title = f"черновик {kind_label(brief.contract_kind)}.md"
        rec = self.archive.add(
            kind="draft",
            filename=title,
            text=markdown,
            contract_kind=brief.contract_kind,
            extra={"status": "draft"},
        )
        in_pc = self.pinecone.upsert_document(
            str(rec["id"]),
            filename=title,
            title=str(rec.get("title") or title),
            contract_kind=brief.contract_kind,
            chunks=[markdown[:4000]],
            role="draft",
            is_example=False,
        )
        self.archive.update(rec["id"], in_pinecone=in_pc, status="draft")
        return markdown

    def _examples_for_draft(self, brief: DraftBrief) -> str:
        """Подборка удачных примеров в промпт генерации (системный ориентир)."""
        from contract_scout.draft import _extract_articles, _split_contract
        from contract_scout.redact import redact_requisites

        self._backfill_examples()
        query = " ".join(
            [
                kind_label(brief.contract_kind),
                brief.subject or "",
                brief.scope or "",
                brief.extra or "",
            ]
        ).strip()
        hits = self.find_similar(query or kind_label(brief.contract_kind), top_k=4, examples_only=True)
        seen: set[str] = set()
        blocks: List[str] = []

        def add_project(pid: str, title_hint: str = "") -> None:
            if not pid or pid in seen or len(blocks) >= 2:
                return
            rec = self.archive.get(pid)
            if not rec or not rec.get("is_example"):
                # допускаем hit из pinecone без локального флага, если текст есть
                if not rec or not (rec.get("text") or "").strip():
                    return
            text = rec.get("text") or ""
            _, body, _ = _split_contract(text)
            body = _extract_articles(body) or body
            body, _ = redact_requisites(body)
            body = (body or "").strip()
            if len(body) < 80:
                return
            seen.add(pid)
            title = title_hint or str(rec.get("title") or "пример")
            blocks.append(f"—— Пример: {title} ——\n{body[:3500]}")

        for hit in hits:
            add_project(str(hit.get("project_id") or ""), str(hit.get("title") or ""))
        if len(blocks) < 2:
            for row in self.list_projects():
                if not row.get("is_example"):
                    continue
                if brief.contract_kind and row.get("contract_kind") not in {brief.contract_kind, "auto", "any"}:
                    # всё же берём тот же тип в приоритете
                    if row.get("contract_kind") != brief.contract_kind:
                        continue
                add_project(str(row.get("id") or ""), str(row.get("title") or ""))
                if len(blocks) >= 2:
                    break
        if not blocks:
            for row in self.list_projects():
                if row.get("is_example"):
                    add_project(str(row.get("id") or ""), str(row.get("title") or ""))
                if len(blocks) >= 2:
                    break
        return "\n\n".join(blocks)

    def revise_draft(self, markdown: str, instruction: str) -> str:
        return self.drafter.revise(markdown, instruction)

    def fix_project_risks(self, project_id: str) -> Dict[str, Any]:
        """Переписать договор по отчёту об узких местах; сохранить как черновик."""
        from contract_scout.redact import redact_requisites

        rec = self.archive.get(project_id)
        if rec is None:
            raise KeyError(project_id)
        if rec.get("kind") == "draft":
            raise RuntimeError("Это уже черновик. Откройте исходный договор с отчётом о рисках.")
        report = rec.get("report") if isinstance(rec.get("report"), dict) else {}
        if not report:
            raise RuntimeError("Сначала проверьте договор (локально или в ИИ).")
        full_text = str(rec.get("text") or "")
        safe_text, _n = redact_requisites(full_text) if self.settings.redact_requisites else (full_text, 0)
        fixed = self.drafter.fix_risks(safe_text or full_text, report)
        kind = str(rec.get("contract_kind") or "services")
        draft_rec = self.archive.add(
            kind="draft",
            filename=f"исправление {rec.get('filename') or 'договор'}.md",
            text=fixed,
            contract_kind=kind,
            extra={
                "status": "draft",
                "source_project_id": project_id,
                "title": f"Исправление: {rec.get('title') or rec.get('filename') or project_id}",
            },
        )
        return {
            "id": draft_rec["id"],
            "source_id": project_id,
            "markdown": fixed,
            "contract_kind": kind,
            "filename": draft_rec.get("filename"),
            "title": draft_rec.get("title"),
        }

    def draft_docx(self, form: Dict[str, Any] | DraftBrief) -> tuple[str, Path, DraftBrief]:
        """Полный черновик в DOCX — без обрезки под лимит чата."""
        brief = form if isinstance(form, DraftBrief) else brief_from_form(form)
        markdown = self.draft(brief)
        dest = self.settings.data_dir / "exports" / f"{uuid.uuid4().hex}.docx"
        self.export_docx(markdown, dest, brief=brief)
        return markdown, dest, brief

    def report_to_file(self, report: Dict[str, Any], *, stem: str = "review") -> Path:
        dest = self.settings.data_dir / "exports" / f"{stem}-{uuid.uuid4().hex[:10]}.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_full_report_text(report), encoding="utf-8")
        return dest

    def export_docx(self, markdown: str, dest: Path, brief: DraftBrief | None = None) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        markdown_to_docx(markdown, dest, brief=brief)
        return dest


def get_app_service() -> ContractScout:
    return ContractScout(load_settings())
