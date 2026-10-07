"""Imports every ORM model so ``Base.metadata`` is complete (Alembic, schema tests)."""

from app.core.models import Base
from app.modules.documents import models as documents_models
from app.modules.messaging import models as messaging_models
from app.modules.notifications import models as notifications_models
from app.modules.numbering import models as numbering_models
from app.modules.public_links import models as public_links_models
from app.modules.rendering import models as rendering_models
from app.modules.tenancy import models as tenancy_models
from app.platform import models as platform_models

__all__ = [
    "Base",
    "documents_models",
    "messaging_models",
    "notifications_models",
    "numbering_models",
    "platform_models",
    "public_links_models",
    "rendering_models",
    "tenancy_models",
]
