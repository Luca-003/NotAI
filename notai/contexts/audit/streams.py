"""Helper per stream_id audit.

Centralizza la convenzione di naming degli stream per evitare:
  - typo (`act:` vs `acts:`),
  - drift quando aggiungiamo un nuovo aggregate,
  - difficolta' a rinominare/spostare in futuro.

Convenzione: `<aggregate>:<id>` dove `<aggregate>` e' un sostantivo singolare.
"""

from __future__ import annotations

import uuid
from typing import Union

IdLike = Union[uuid.UUID, str]


def _s(v: IdLike) -> str:
    return str(v)


def stream_for_act(act_id: IdLike) -> str:
    return f"act:{_s(act_id)}"


def stream_for_practice(practice_id: IdLike) -> str:
    return f"practice:{_s(practice_id)}"


def stream_for_document(document_id: IdLike) -> str:
    return f"document:{_s(document_id)}"


def stream_for_provenance(output_document_id: IdLike) -> str:
    return f"provenance:{_s(output_document_id)}"


def stream_for_act_example(example_id: IdLike) -> str:
    return f"act-example:{_s(example_id)}"


def stream_for_tenant_config(tenant_id: IdLike) -> str:
    return f"tenant-config:{_s(tenant_id)}"


__all__ = [
    "stream_for_act",
    "stream_for_practice",
    "stream_for_document",
    "stream_for_provenance",
    "stream_for_act_example",
    "stream_for_tenant_config",
]
