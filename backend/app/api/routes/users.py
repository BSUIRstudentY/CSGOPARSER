"""Saved filters, searches, and alert definitions.

Alerts are stored for a future notifier. This version does not send Telegram or Discord messages.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import Alert, SavedSearch, User, UserSettings
from app.schemas.market import (
    AlertIn,
    AlertOut,
    AlertUpdate,
    FiltersPayload,
    SavedSearchIn,
    SavedSearchOut,
    SettingsOut,
    SettingsUpdate,
)

router = APIRouter(tags=["users"])


async def _settings(db: AsyncSession, user: User) -> UserSettings:
    row = await db.get(UserSettings, user.id)
    if row is None:
        row = UserSettings(user_id=user.id, default_filters={})
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def _filters(payload: dict[str, object] | None) -> FiltersPayload:
    return FiltersPayload.model_validate(payload or {})


@router.get("/settings", response_model=SettingsOut)
async def get_settings_route(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SettingsOut:
    row = await _settings(db, user)
    return SettingsOut(default_filters=_filters(row.default_filters))


@router.put("/settings", response_model=SettingsOut)
async def update_settings(
    payload: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SettingsOut:
    row = await _settings(db, user)
    row.default_filters = payload.default_filters.model_dump()
    await db.commit()
    return SettingsOut(default_filters=payload.default_filters)


@router.get("/saved-searches", response_model=list[SavedSearchOut])
async def list_searches(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SavedSearchOut]:
    rows = (
        (
            await db.execute(
                select(SavedSearch)
                .where(SavedSearch.user_id == user.id)
                .order_by(SavedSearch.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        SavedSearchOut(
            id=row.id,
            name=row.name,
            filters=_filters(row.filters),
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/saved-searches", response_model=SavedSearchOut, status_code=201)
async def create_search(
    payload: SavedSearchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SavedSearchOut:
    row = SavedSearch(user_id=user.id, name=payload.name, filters=payload.filters.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SavedSearchOut(
        id=row.id, name=row.name, filters=payload.filters, created_at=row.created_at
    )


@router.delete("/saved-searches/{search_id}", status_code=204)
async def delete_search(
    search_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    row = await db.get(SavedSearch, search_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Saved search not found")
    await db.delete(row)
    await db.commit()


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AlertOut]:
    rows = (
        (
            await db.execute(
                select(Alert).where(Alert.user_id == user.id).order_by(Alert.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_alert_out(row) for row in rows]


@router.post("/alerts", response_model=AlertOut, status_code=201)
async def create_alert(
    payload: AlertIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlertOut:
    row = Alert(
        user_id=user.id,
        name=payload.name,
        filters=payload.filters.model_dump(),
        channel=payload.channel,
        enabled=payload.enabled,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _alert_out(row)


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: int,
    payload: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlertOut:
    row = await db.get(Alert, alert_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Alert not found")
    data = payload.model_dump(exclude_unset=True)
    if "filters" in data and data["filters"] is not None:
        data["filters"] = payload.filters.model_dump() if payload.filters else {}
    for key, value in data.items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return _alert_out(row)


@router.delete("/alerts/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    row = await db.get(Alert, alert_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(row)
    await db.commit()


def _alert_out(row: Alert) -> AlertOut:
    return AlertOut(
        id=row.id,
        name=row.name,
        filters=_filters(row.filters),
        channel=row.channel,
        enabled=row.enabled,
        created_at=row.created_at,
    )
