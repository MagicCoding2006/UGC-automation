"""Protocol-level mocks test paid transport without making paid requests."""
import json
import pytest


def test_fal_complete_then_resume_reuses_provider_request(workspace,batch_spec,monkeypatch):
    from ugc import config,db,providers
    from ugc.service import make_batch
    make_batch(batch_spec)
    job=db.one('SELECT * FROM jobs')
    monkeypatch.setattr(config,'MODE','production')
    monkeypatch.setenv('FAL_KEY','test-no-network')
    calls=[]
    class Reply:
        is_error=False
        status_code=200
        def __init__(self,data): self.data=data
        def raise_for_status(self): pass
        def json(self): return self.data
    class Client:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,url,**kw):
            calls.append(('POST',url))
            return Reply(dict(request_id='existing',status_url='https://queue.fal.run/test/model/requests/existing/status',response_url='https://queue.fal.run/test/model/requests/existing'))
        def get(self,url,**kw):
            calls.append(('GET',url))
            return Reply(dict(status='COMPLETED') if url.endswith('/status') else dict(video={'url':'https://fal.media/result.mp4'}))
    monkeypatch.setattr(providers.httpx,'Client',Client)
    for _ in range(2):
        result=providers.fal(job,'video','test/model',{},.5,'key')
        assert result['video']['url']=='https://fal.media/result.mp4'
    assert len([c for c in calls if c[0]=='POST'])==1
    assert db.one('SELECT COUNT(*) n FROM spend')['n']==1


def test_lost_fal_submit_response_stays_unknown(workspace,batch_spec,monkeypatch):
    from ugc import config,db,providers
    from ugc.service import make_batch
    make_batch(batch_spec)
    job=db.one('SELECT * FROM jobs')
    monkeypatch.setattr(config,'MODE','production')
    monkeypatch.setenv('FAL_KEY','test-no-network')
    calls=[]
    class Client:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**kw):
            calls.append('POST')
            raise OSError('connection lost after send')
    monkeypatch.setattr(providers.httpx,'Client',Client)
    for _ in range(2):
        with pytest.raises(providers.NeedsAttention):
            providers.fal(job,'video','test/model',{},.5,'key')
    assert calls==['POST']
    assert db.one('SELECT * FROM requests')['state']=='submitting'
    assert db.one('SELECT SUM(amount) n FROM spend')['n']==pytest.approx(.5)
