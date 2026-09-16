"""Build a conservative contract -> PO -> invoice relationship view."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable


_SOW_RE = re.compile(
    r"(?:statement[\s_-]*of[\s_-]*work|\bsow\b)[\s#:_-]*([A-Z0-9][A-Z0-9./-]{1,})",
    re.IGNORECASE,
)
_INVOICE_RE = re.compile(
    r"(?:invoice|\binv\b)[\s#:_-]*([A-Z0-9][A-Z0-9./-]{1,})",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _reference(pattern: re.Pattern[str], filename: str) -> str | None:
    match = pattern.search(filename)
    if not match:
        return None
    raw_value = match.group(1)
    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if extension and raw_value.casefold() == extension.casefold():
        return None
    value = re.sub(r"\.[a-z0-9]{1,8}$", "", raw_value, flags=re.IGNORECASE)
    value = value.rstrip(".-_/")
    return value or None


def _document_kind(filename: str) -> str:
    lowered = _text(filename).casefold()
    if re.search(r"statement[\s_-]*of[\s_-]*work|\bsow\b", lowered):
        return "sow"
    if re.search(r"invoice|\binv\b", lowered):
        return "invoice"
    return "document"


def _sow_candidate(row: dict[str, Any]) -> tuple[str | None, str, str]:
    filename = _text(row.get("attachment_name"))
    reference = _reference(_SOW_RE, filename)
    if reference:
        return f"SOW:{reference.casefold()}", reference, "explicit filename reference"
    digest = _text(row.get("sha256")).casefold()
    if digest and _document_kind(filename) == "sow":
        return f"SOW-HASH:{digest}", "SOW number not identified", "exact document hash candidate"
    return None, "SOW not identified", "no SOW evidence"


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _invoice_reference(row: dict[str, Any]) -> tuple[str, str]:
    filename = _text(row.get("attachment_name"))
    reference = _reference(_INVOICE_RE, filename)
    if reference:
        return reference, "explicit filename reference"
    return filename or "Invoice document", "invoice filename only"


def build_lab_relationships(
    pos: Iterable[dict[str, Any]],
    attachments: Iterable[dict[str, Any]],
    powerbi_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return tree rows and cardinality checks for the LAB relationship view.

    The local database stores the contract evidence and downloaded PO records.
    When ``powerbi_data`` is present, PO commitment and invoice children come
    from the existing Power BI datasets.
    """
    po_rows = {_text(row.get("po_number")): dict(row) for row in pos if _text(row.get("po_number"))}
    powerbi_pos = (powerbi_data or {}).get("pos") or {}
    powerbi_invoices = (powerbi_data or {}).get("invoices") or {}
    using_powerbi = powerbi_data is not None
    attachments_by_po: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in attachments:
        row = dict(raw)
        po = _text(row.get("po_number"))
        if po in po_rows:
            attachments_by_po[po].append(row)

    sow_by_po: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    invoice_by_po: dict[str, list[dict[str, Any]]] = defaultdict(list)
    invoice_owners: dict[str, set[str]] = defaultdict(set)
    sow_owners: dict[str, set[str]] = defaultdict(set)
    document_count = 0

    for po, rows in attachments_by_po.items():
        for row in rows:
            filename = _text(row.get("attachment_name")) or "Unnamed document"
            kind = _document_kind(filename)
            document_count += 1
            if kind == "sow":
                key, label, evidence = _sow_candidate(row)
                if key:
                    sow_by_po[po][key] = {
                        "key": key,
                        "label": label,
                        "evidence": evidence,
                    }
                    sow_owners[key].add(po)
                continue
            if kind != "invoice":
                continue
            reference, evidence = _invoice_reference(row)
            invoice_key = f"INVOICE:{reference.casefold()}"
            invoice_owners[invoice_key].add(po)
            invoice_by_po[po].append({
                "key": f"{invoice_key}:{row.get('id', filename)}",
                "label": reference,
                "filename": filename,
                "kind": "invoice",
                "evidence": evidence,
                "sha256": _text(row.get("sha256")),
            })

    if using_powerbi:
        invoice_by_po.clear()
        invoice_owners.clear()
        for po in po_rows:
            for index, raw in enumerate(powerbi_invoices.get(po, []), start=1):
                invoice = dict(raw) if isinstance(raw, dict) else {}
                invoice_number = _text(invoice.get("invoice_number"))
                accounting_document = _text(invoice.get("accounting_document_number"))
                identity = invoice_number or accounting_document or f"row-{index}"
                relationship_key = f"INVOICE:{identity.casefold()}"
                invoice_by_po[po].append({
                    **invoice,
                    "key": f"{relationship_key}:{po}:{index}",
                    "label": invoice_number or accounting_document or "Invoice document",
                    "kind": "invoice",
                    "evidence": "Power BI Invoice dataset",
                    "source": "Power BI Invoice dataset",
                    "invoice_number": invoice_number,
                    "accounting_document_number": accounting_document,
                })
                invoice_owners[relationship_key].add(po)

    warnings: list[dict[str, Any]] = []
    for po in sorted(po_rows):
        sows = sow_by_po.get(po, {})
        if len(sows) > 1:
            warnings.append({
                "code": "po_multiple_sows",
                "severity": "error",
                "message": f"PO {po} is associated with {len(sows)} SOW candidates.",
                "po_number": po,
            })
        if not sows:
            warnings.append({
                "code": "po_missing_sow",
                "severity": "warning",
                "message": f"PO {po} has no identifiable SOW document.",
                "po_number": po,
            })
        if not invoice_by_po.get(po):
            warnings.append({
                "code": "po_missing_invoice",
                "severity": "warning",
                "message": f"PO {po} has no identifiable invoice document.",
                "po_number": po,
            })

    for invoice_key, owners in sorted(invoice_owners.items()):
        if len(owners) > 1:
            warnings.append({
                "code": "invoice_multiple_pos",
                "severity": "error",
                "message": f"Invoice {invoice_key.removeprefix('INVOICE:')} appears under multiple POs.",
                "po_numbers": sorted(owners),
            })

    grouped: dict[str, dict[str, Any]] = {}
    for po, row in sorted(po_rows.items()):
        sow_entries = list(sow_by_po.get(po, {}).values())
        if sow_entries:
            for sow in sow_entries:
                group = grouped.setdefault(sow["key"], {
                    "key": sow["key"],
                    "label": sow["label"],
                    "evidence": sow["evidence"],
                    "pos": [],
                })
                group["pos"].append(po)
        else:
            group = grouped.setdefault("SOW:__unlinked__", {
                "key": "SOW:__unlinked__",
                "label": "SOW not identified",
                "evidence": "missing relationship key",
                "pos": [],
            })
            group["pos"].append(po)

    trees = []
    for sow in sorted(grouped.values(), key=lambda item: item["label"].casefold()):
        children = []
        for po in sorted(sow["pos"]):
            row = po_rows[po]
            commitment = powerbi_pos.get(po, {}).get("commitment_value_eur") if using_powerbi else None
            documents = [
                {
                    "key": f"DOCUMENT:{po}:{item.get('id', item.get('attachment_name', index))}",
                    "label": _text(item.get("attachment_name")) or "Unnamed document",
                    "kind": _document_kind(_text(item.get("attachment_name"))),
                    "evidence": "downloaded attachment",
                }
                for index, item in enumerate(attachments_by_po.get(po, []))
                if not (using_powerbi and _document_kind(_text(item.get("attachment_name"))) == "invoice")
            ]
            child = {
                "key": f"PO:{po}",
                "label": po,
                "kind": "po",
                "status": _text(row.get("status")) or "UNKNOWN",
                "company_code": _text(row.get("company_code")),
                "documents": documents,
                "invoices": invoice_by_po.get(po, []),
                "sow_count": len(sow_by_po.get(po, {})),
            }
            if commitment is not None:
                child["commitment_value_eur"] = _number(commitment)
            children.append(child)
        tree = {
            "key": sow["key"],
            "label": sow["label"],
            "kind": "sow",
            "evidence": sow["evidence"],
            "pos": children,
        }
        if using_powerbi:
            tree["commitment_total_eur"] = sum(
                _number(item.get("commitment_value_eur")) for item in children
            )
        trees.append(tree)

    return {
        "tree": trees,
        "summary": {
            "sows": len([item for item in trees if item["key"] != "SOW:__unlinked__"]),
            "pos": len(po_rows),
            "invoices": sum(len(items) for items in invoice_by_po.values()),
            "documents": document_count,
            "warnings": len(warnings),
            "errors": sum(1 for item in warnings if item["severity"] == "error"),
        },
        "validation": warnings,
        "sources": {
            "contract": "Coupa downloaded attachment filename and SHA-256",
            "po": "Power BI PO dataset" if using_powerbi else "Local SQLite PO records",
            "invoice": "Power BI Invoice dataset" if using_powerbi else "Local attachment filenames",
        },
    }
