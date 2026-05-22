"""Registra tutti i modelli SQLAlchemy in un singolo punto.

Importare questo modulo (anche solo via `import notai.models`) garantisce
che TUTTE le tabelle e le relazioni FK siano note al metadata prima di
qualunque operazione DB. Necessario perche' i contesti si referenziano
incrociatamente (es. Practice.main_client_party_id -> Party.id).
"""

from __future__ import annotations

# Import side-effect: ogni `from <ctx>.models import *` registra le tabelle.
from notai.contexts.audit.models import (  # noqa: F401
    AuditEvent,
    LLMInvocation,
)
from notai.contexts.documents.models import (  # noqa: F401
    Document,
    DocumentChunk,
    ProvenanceLink,
)
from notai.contexts.drafting.examples_models import ActExample  # noqa: F401
from notai.contexts.iam.models import (  # noqa: F401
    Permission,
    Role,
    RolePermission,
    Tenant,
    User,
    UserRole,
)
from notai.contexts.modules.models import FeatureFlag  # noqa: F401
from notai.contexts.parties.models import (  # noqa: F401
    AMLAssessment,
    Party,
)
from notai.contexts.practices.models import (  # noqa: F401
    Act,
    PartyRole,
    Practice,
)
from notai.contexts.search.models import (  # noqa: F401
    Clause,
    NormativeReference,
    Tag,
    TaggedItem,
)
