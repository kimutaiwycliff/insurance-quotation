"""Imports every ORM model so ``Base.metadata`` is complete (Alembic, schema tests)."""

from app.core.models import Base
from app.modules.numbering import models as numbering_models
from app.modules.tenancy import models as tenancy_models
from app.platform import models as platform_models

__all__ = ["Base", "numbering_models", "platform_models", "tenancy_models"]
