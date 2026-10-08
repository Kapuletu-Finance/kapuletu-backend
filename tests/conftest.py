"""
Shared test fixtures. The finance ones give an in-memory SQLite database with the tables billing touches,
and switch off side effects (emails, notifications).
"""
import pytest
from finance_support import FINANCE_MODELS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.base import Base


@pytest.fixture
def Session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[m.__table__ for m in FINANCE_MODELS])
    return sessionmaker(bind=engine)


@pytest.fixture
def db(Session):
    session = Session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch):
    import common.system_config_service as config_service
    import services.finance.fulfillment as fulfillment
    import services.notifications.admin_dispatcher as dispatcher

    config_service._CONFIG_CACHE.clear()
    monkeypatch.setattr(fulfillment, "create_notification", lambda **kwargs: None)
    monkeypatch.setattr(fulfillment.FulfillmentService, "_notify_admins", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(dispatcher, "notify_admins_async", lambda *a, **k: None)
