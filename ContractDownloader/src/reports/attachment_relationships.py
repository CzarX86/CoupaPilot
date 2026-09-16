"""Build conservative cross-PO attachment relationship reports."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable


def _filename_key(value: str) -> str:
    value = str(value or "").strip().casefold()
    value = re.sub(r"\s+", " ", value)
    return value


def build_attachment_relationships(
    attachments: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return groups of POs sharing an attachment hash or filename.

    Hash matches are exact-content evidence. Filename-only matches are
    intentionally reported as a weaker lead for human review, not as proof
    that two POs belong to the same contract.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in attachments:
        po = str(row.get("po_number") or "").strip()
        name = str(row.get("attachment_name") or "").strip()
        if not po or not name:
            continue
        digest = str(row.get("sha256") or "").strip().lower()
        if digest:
            groups[("SHA256", digest)].append(row)
        key = _filename_key(name)
        if key:
            groups[("FILENAME", key)].append(row)

    result: list[dict[str, Any]] = []
    for (match_type, match_key), rows in groups.items():
        pos = sorted({str(row.get("po_number") or "").strip() for row in rows if row.get("po_number")})
        if len(pos) < 2:
            continue
        names = sorted({str(row.get("attachment_name") or "").strip() for row in rows})
        result.append({
            "MATCH_TYPE": match_type,
            "MATCH_KEY": match_key if match_type == "SHA256" else names[0],
            "PO_COUNT": len(pos),
            "PO_NUMBERS": " | ".join(pos),
            "ATTACHMENT_NAMES": " | ".join(names),
            "CONFIDENCE": "Exact content" if match_type == "SHA256" else "Review filename match",
            "RECOMMENDATION": (
                "Investigate as a shared contract candidate."
                if match_type == "SHA256"
                else "Compare document content before grouping the contract."
            ),
        })
    return sorted(result, key=lambda row: (0 if row["MATCH_TYPE"] == "SHA256" else 1, row["MATCH_KEY"]))
