"""The signed-in user's notifications and preferences (every member may use these)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.pagination import Page, PageParams, build_page, page_params
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationOut, Preference, UnreadCount
from app.platform.deps import TenantContext, require_permission

router = APIRouter(tags=["notifications"])
# Own notifications only (queries filter by the principal), so no permission beyond membership.
Me = Annotated[TenantContext, Depends(require_permission(None))]


@router.get("/notifications", operation_id="notifications_list")
async def list_notifications(
    ctx: Me, page: Annotated[PageParams, Depends(page_params)], unread_only: bool = False
) -> Page[NotificationOut]:
    rows = await service.list_mine(
        ctx.session,
        ctx.principal.user_id,
        cursor=page.cursor,
        limit=page.limit,
        unread_only=unread_only,
    )
    return build_page(
        [NotificationOut.model_validate(r) for r in rows], [r.id for r in rows], page.limit
    )


@router.get("/notifications/unread-count", operation_id="notifications_unread_count")
async def unread(ctx: Me) -> UnreadCount:
    return UnreadCount(unread=await service.unread_count(ctx.session, ctx.principal.user_id))


@router.post(
    "/notifications/{notification_id}/read", operation_id="notifications_read", status_code=204
)
async def read_one(ctx: Me, notification_id: uuid.UUID) -> None:
    await service.mark_read(ctx.session, ctx.principal.user_id, notification_id)


@router.post("/notifications/read-all", operation_id="notifications_read_all")
async def read_all(ctx: Me) -> UnreadCount:
    await service.mark_read(ctx.session, ctx.principal.user_id, None)
    return UnreadCount(unread=0)


@router.get("/notification-preferences", operation_id="notification_preferences_get")
async def get_preferences(ctx: Me) -> list[Preference]:
    return await service.get_preferences(ctx.session, ctx.principal.user_id)


@router.put("/notification-preferences", operation_id="notification_preferences_set")
async def set_preferences(ctx: Me, body: list[Preference]) -> list[Preference]:
    return await service.set_preferences(ctx.session, ctx.tenant_id, ctx.principal.user_id, body)
