from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from pydantic import BaseModel
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

REQUIRED_LINEAGE_FIELDS = (
    "license_tag",
    "usage_scope",
    "redistribution_scope",
    "source_uri",
    "lineage_hash",
)


def canonicalize_payload(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def compute_lineage_hash(payload: Any) -> str:
    return sha256(canonicalize_payload(payload).encode("utf-8")).hexdigest()


def build_lineage(
    payload: Any,
    *,
    source_uri: str,
    license_tag: str,
    usage_scope: str,
    redistribution_scope: str,
) -> dict[str, str]:
    fields = {
        "license_tag": license_tag,
        "usage_scope": usage_scope,
        "redistribution_scope": redistribution_scope,
        "source_uri": source_uri,
        "lineage_hash": compute_lineage_hash(payload),
    }
    missing = [key for key, value in fields.items() if not value]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Missing required lineage fields: {joined}")
    return fields


class LineageMixin:
    license_tag: Mapped[str] = mapped_column(String(64), nullable=False)
    usage_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    redistribution_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    lineage_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class LineageRecord(BaseModel):
    license_tag: str
    usage_scope: str
    redistribution_scope: str
    source_uri: str
    lineage_hash: str
