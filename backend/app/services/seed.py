from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import HangRail, RailPlacement, Store, WorkOrder


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Store.id).limit(1)):
        return
    store = Store(name="清风干洗 · 滨江店")
    db.add(store)
    db.flush()
    r1 = HangRail(store_id=store.id, label="A 杆", length_cm=200)
    r2 = HangRail(store_id=store.id, label="B 杆", length_cm=160)
    db.add_all([r1, r2])
    db.flush()
    now = datetime.utcnow()
    orders = [
        WorkOrder(store_id=store.id, ticket_code="HR-2001", garment_name="羊毛大衣", length_cm=45, status="hung", due_at=now + timedelta(days=1), hung_at=now - timedelta(hours=5)),
        WorkOrder(store_id=store.id, ticket_code="HR-2002", garment_name="西装套装", length_cm=35, status="hung", due_at=now + timedelta(days=2), hung_at=now - timedelta(hours=3)),
        WorkOrder(store_id=store.id, ticket_code="HR-2003", garment_name="羽绒服", length_cm=50, status="ready", due_at=now + timedelta(days=1)),
        WorkOrder(store_id=store.id, ticket_code="HR-2004", garment_name="连衣裙", length_cm=30, status="ready", due_at=now - timedelta(days=1)),
        WorkOrder(store_id=store.id, ticket_code="HR-2005", garment_name="风衣", length_cm=40, status="hung", due_at=now - timedelta(hours=12), hung_at=now - timedelta(days=3)),
    ]
    db.add_all(orders)
    db.flush()
    # HR-2001 已由 A 杆移至 B 杆：A 杆 [0,45] 为失效历史占位，B 杆 [40,85] 为现占位（First-Fit 空位）
    db.add_all(
        [
            RailPlacement(rail_id=r1.id, order_id=orders[0].id, start_cm=0, end_cm=45, active=0),
            RailPlacement(rail_id=r1.id, order_id=orders[1].id, start_cm=45, end_cm=80),
            RailPlacement(rail_id=r2.id, order_id=orders[4].id, start_cm=0, end_cm=40),
            RailPlacement(rail_id=r2.id, order_id=orders[0].id, start_cm=40, end_cm=85),
        ]
    )
    db.commit()
