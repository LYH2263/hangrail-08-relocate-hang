import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import HangRail, RailPlacement, Store, WorkOrder


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # 不使用 with：避免触发 lifespan 去连真实数据库；get_db 已被覆盖。
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_store(db, name="测试门店"):
    store = Store(name=name)
    db.add(store)
    db.flush()
    return store


def _make_rail(db, store, label, length_cm):
    rail = HangRail(store_id=store.id, label=label, length_cm=length_cm)
    db.add(rail)
    db.flush()
    return rail


def _make_hung_order(db, store, ticket, length_cm):
    from datetime import datetime, timedelta

    order = WorkOrder(
        store_id=store.id,
        ticket_code=ticket,
        garment_name="测试衣物",
        length_cm=length_cm,
        status="hung",
        due_at=datetime.utcnow() + timedelta(days=1),
        hung_at=datetime.utcnow(),
    )
    db.add(order)
    db.flush()
    return order


def _placement(db, rail, order, start, end, active=1):
    p = RailPlacement(
        rail_id=rail.id, order_id=order.id, start_cm=start, end_cm=end, active=active
    )
    db.add(p)
    db.flush()
    return p


def _active_placements(db, order_id):
    return db.scalars(
        select(RailPlacement).where(
            RailPlacement.order_id == order_id, RailPlacement.active == 1
        )
    ).all()


def test_move_target_full_keeps_origin(client, db_session):
    store = _make_store(db_session)
    rail_a = _make_rail(db_session, store, "A 杆", 100)
    rail_b = _make_rail(db_session, store, "B 杆", 50)
    order = _make_hung_order(db_session, store, "MV-001", 40)
    origin = _placement(db_session, rail_a, order, 0, 40)
    # B 杆仅剩 15-20 一个 5cm 空隙，40cm 衣物放不下
    blocker1 = _make_hung_order(db_session, store, "MV-B1", 15)
    _placement(db_session, rail_b, blocker1, 0, 15)
    blocker2 = _make_hung_order(db_session, store, "MV-B2", 30)
    _placement(db_session, rail_b, blocker2, 20, 50)
    db_session.commit()

    res = client.post(
        "/api/move", json={"order_id": order.id, "target_rail_id": rail_b.id}
    )
    assert res.status_code == 409

    db_session.expire_all()
    active = _active_placements(db_session, order.id)
    # 目标不足：原占位不动，仍只在 A 杆 active
    assert len(active) == 1
    assert active[0].rail_id == rail_a.id
    assert (active[0].start_cm, active[0].end_cm) == (0, 40)
    assert db_session.get(RailPlacement, origin.id).active == 1
    assert (
        db_session.scalar(
            select(RailPlacement.id).where(
                RailPlacement.rail_id == rail_b.id,
                RailPlacement.order_id == order.id,
            )
        )
        is None
    )


def test_move_success_only_target_active(client, db_session):
    store = _make_store(db_session)
    rail_a = _make_rail(db_session, store, "A 杆", 100)
    rail_b = _make_rail(db_session, store, "B 杆", 100)
    order = _make_hung_order(db_session, store, "MV-100", 40)
    origin = _placement(db_session, rail_a, order, 0, 40)
    blocker = _make_hung_order(db_session, store, "MV-BX", 30)
    _placement(db_session, rail_b, blocker, 0, 30)
    db_session.commit()

    res = client.post(
        "/api/move", json={"order_id": order.id, "target_rail_id": rail_b.id}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "hung"

    db_session.expire_all()
    active = _active_placements(db_session, order.id)
    # 成功后仅目标杆 active，不存在双杆同时 active
    assert len(active) == 1
    assert active[0].rail_id == rail_b.id
    # First-Fit：落到 B 杆首个空位 [30,70]
    assert (active[0].start_cm, active[0].end_cm) == (30, 70)
    assert db_session.get(RailPlacement, origin.id).active == 0


def test_move_cross_store_rejected(client, db_session):
    store1 = _make_store(db_session, "门店一")
    store2 = _make_store(db_session, "门店二")
    rail_a = _make_rail(db_session, store1, "A 杆", 100)
    rail_other = _make_rail(db_session, store2, "跨店杆", 100)
    order = _make_hung_order(db_session, store1, "MV-200", 40)
    origin = _placement(db_session, rail_a, order, 0, 40)
    db_session.commit()

    res = client.post(
        "/api/move", json={"order_id": order.id, "target_rail_id": rail_other.id}
    )
    assert res.status_code == 400

    db_session.expire_all()
    active = _active_placements(db_session, order.id)
    assert len(active) == 1
    assert active[0].rail_id == rail_a.id
    assert db_session.get(RailPlacement, origin.id).active == 1


def test_move_requires_hung_status(client, db_session):
    from datetime import datetime, timedelta

    store = _make_store(db_session)
    rail_b = _make_rail(db_session, store, "B 杆", 100)
    order = WorkOrder(
        store_id=store.id,
        ticket_code="MV-300",
        garment_name="测试衣物",
        length_cm=40,
        status="ready",
        due_at=datetime.utcnow() + timedelta(days=1),
    )
    db_session.add(order)
    db_session.commit()

    res = client.post(
        "/api/move", json={"order_id": order.id, "target_rail_id": rail_b.id}
    )
    assert res.status_code == 400
