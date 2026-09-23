from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.models import HangRail, RailPlacement, Store, WorkOrder


def _make_store(db, name="测试店"):
    store = Store(name=name)
    db.add(store)
    db.flush()
    return store


def _make_rail(db, store, label, length):
    rail = HangRail(store_id=store.id, label=label, length_cm=length)
    db.add(rail)
    db.flush()
    return rail


def _hang(db, store, rail, ticket, length, start=None):
    now = datetime.utcnow()
    order = WorkOrder(
        store_id=store.id,
        ticket_code=ticket,
        garment_name="测试衣物",
        length_cm=length,
        status="hung",
        due_at=now + timedelta(days=1),
        hung_at=now,
    )
    db.add(order)
    db.flush()
    if start is None:
        start = 0.0
    db.add(
        RailPlacement(
            rail_id=rail.id, order_id=order.id, start_cm=start, end_cm=start + length, active=1
        )
    )
    db.commit()
    return order


def _active(db, order_id):
    return db.scalars(
        select(RailPlacement).where(
            RailPlacement.order_id == order_id, RailPlacement.active == 1
        )
    ).all()


def test_move_insufficient_target_keeps_original(client, db):
    store = _make_store(db)
    a = _make_rail(db, store, "A 杆", 100)
    b = _make_rail(db, store, "B 杆", 100)
    # B 杆仅余 20cm 空隙，放不下 40cm 的工单
    blocker = _hang(db, store, b, "HR-B1", 80)
    order = _hang(db, store, a, "HR-A1", 40)

    resp = client.post("/api/move", json={"order_id": order.id, "target_rail_id": b.id})
    assert resp.status_code == 409

    db.expire_all()
    actives = _active(db, order.id)
    assert len(actives) == 1
    assert actives[0].rail_id == a.id
    assert (actives[0].start_cm, actives[0].end_cm) == (0.0, 40.0)
    # 目标杆上没有出现该工单的任何占位
    assert not db.scalars(
        select(RailPlacement).where(
            RailPlacement.order_id == order.id, RailPlacement.rail_id == b.id
        )
    ).all()
    # 阻挡衣物也不受影响
    blocker_actives = _active(db, blocker.id)
    assert len(blocker_actives) == 1 and blocker_actives[0].rail_id == b.id


def test_move_success_only_target_rail_active(client, db):
    store = _make_store(db)
    a = _make_rail(db, store, "A 杆", 100)
    b = _make_rail(db, store, "B 杆", 100)
    other = _hang(db, store, b, "HR-B1", 30)
    order = _hang(db, store, a, "HR-A1", 40)

    resp = client.post("/api/move", json={"order_id": order.id, "target_rail_id": b.id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "hung"

    db.expire_all()
    actives = _active(db, order.id)
    assert len(actives) == 1
    p = actives[0]
    assert p.rail_id == b.id
    # First-Fit：B 杆 0-30 已被占，新段紧跟其后
    assert (p.start_cm, p.end_cm) == (30.0, 70.0)
    # 原 A 杆段已释放（保留为 inactive 历史行）
    old = db.scalars(
        select(RailPlacement).where(
            RailPlacement.order_id == order.id, RailPlacement.rail_id == a.id
        )
    ).all()
    assert len(old) == 1 and old[0].active == 0
    # 其他工单占位不受影响
    other_actives = _active(db, other.id)
    assert len(other_actives) == 1 and (other_actives[0].start_cm, other_actives[0].end_cm) == (0.0, 30.0)


def test_move_cross_store_rejected(client, db):
    s1 = _make_store(db, "甲店")
    s2 = _make_store(db, "乙店")
    a = _make_rail(db, s1, "A 杆", 100)
    b = _make_rail(db, s2, "B 杆", 200)
    order = _hang(db, s1, a, "HR-A1", 40)

    resp = client.post("/api/move", json={"order_id": order.id, "target_rail_id": b.id})
    assert resp.status_code == 400

    db.expire_all()
    actives = _active(db, order.id)
    assert len(actives) == 1
    assert actives[0].rail_id == a.id


def test_move_requires_hung_status(client, db):
    store = _make_store(db)
    a = _make_rail(db, store, "A 杆", 100)
    b = _make_rail(db, store, "B 杆", 100)
    now = datetime.utcnow()
    order = WorkOrder(
        store_id=store.id,
        ticket_code="HR-READY",
        garment_name="未上杆",
        length_cm=40,
        status="ready",
        due_at=now + timedelta(days=1),
    )
    db.add(order)
    db.commit()

    resp = client.post("/api/move", json={"order_id": order.id, "target_rail_id": b.id})
    assert resp.status_code == 400
