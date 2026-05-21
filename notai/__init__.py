"""NotAI - core package."""

# Garantisce che tutti i modelli SQLAlchemy siano registrati al primo import
# del package, per evitare errori di FK non risolta quando i contesti si
# referenziano incrociatamente.
from notai import models as _models  # noqa: F401
