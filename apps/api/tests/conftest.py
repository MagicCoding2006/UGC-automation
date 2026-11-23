import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['UGC_MODE']='demo'
os.environ['UGC_TOKEN']=''


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    from ugc import config,db
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'MEDIA',tmp_path/'media')
    monkeypatch.setattr(config,'DB',tmp_path/'db.sqlite3')
    monkeypatch.setattr(config,'MODE','demo')
    monkeypatch.setattr(config,'TOKEN','')
    monkeypatch.setattr(config,'DAILY_BUDGET',25)
    monkeypatch.setattr(config,'RESOLUTION',360)
    config.MEDIA.mkdir()
    db.initialize()
    return tmp_path


@pytest.fixture
def client(workspace):
    from fastapi.testclient import TestClient
    from ugc.main import app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def batch_spec(workspace):
    from ugc import db
    from ugc.schemas import Batch
    return Batch(name='Test batch',product_id='example-bottle',creator_ids=[db.rows('SELECT * FROM creators')[0]['id']],models=['demo'],count=3,budget=10)
