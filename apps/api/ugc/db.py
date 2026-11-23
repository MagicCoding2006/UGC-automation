"""SQLite WAL queue: multiple CPU/remote workers can share one local disk.

Never put SQLite on NFS. Split deployments by keeping API + queue workers on
one host; inference services are stateless HTTP workers on other hosts.
"""
import contextlib
import json
import sqlite3
import time
import uuid
from . import config


def uid(prefix=''):
    return prefix + uuid.uuid4().hex[:16]


@contextlib.contextmanager
def connection(write=False):
    conn = sqlite3.connect(config.DB, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=30000')
    try:
        if write:
            conn.execute('BEGIN IMMEDIATE')
        yield conn
        if write:
            conn.commit()
    except BaseException:
        if write:
            conn.rollback()
        raise
    finally:
        conn.close()


JSON_FIELDS = {'data', 'spec', 'qa', 'payload', 'result'}


def decode(row):
    if row is None:
        return None
    item = dict(row)
    for key in JSON_FIELDS & item.keys():
        item[key] = json.loads(item[key]) if item[key] else None
    return item


def rows(sql, args=()):
    with connection() as c:
        return [decode(r) for r in c.execute(sql, args).fetchall()]


def one(sql, args=()):
    with connection() as c:
        return decode(c.execute(sql, args).fetchone())


def execute(sql, args=()):
    with connection(True) as c:
        c.execute(sql, args)


def event(job_id, stage, message, kind='info'):
    execute('INSERT INTO events(job_id,stage,message,kind,created) VALUES(?,?,?,?,?)',
            (job_id, stage, message, kind, time.time()))


def initialize():
    with connection() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS products (
          id TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS creators (
          id TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS assets (
          id TEXT PRIMARY KEY, product_id TEXT REFERENCES products(id), kind TEXT NOT NULL,
          path TEXT NOT NULL, name TEXT NOT NULL, rights TEXT NOT NULL,
          approved INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS batches (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, product_id TEXT REFERENCES products(id),
          spec TEXT NOT NULL, budget REAL NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, batch_id TEXT REFERENCES batches(id),
          status TEXT NOT NULL DEFAULT 'queued', stage TEXT NOT NULL DEFAULT 'queued',
          spec TEXT NOT NULL, result TEXT, qa TEXT, error TEXT,
          attempts INTEGER NOT NULL DEFAULT 0, cancel_requested INTEGER NOT NULL DEFAULT 0,
          owner TEXT, lease REAL, available REAL NOT NULL DEFAULT 0,
          created REAL NOT NULL, updated REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS job_claim ON jobs(status, available, created);
        CREATE INDEX IF NOT EXISTS job_batch ON jobs(batch_id);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT REFERENCES jobs(id),
          stage TEXT NOT NULL, message TEXT NOT NULL, kind TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS spend (
          id TEXT PRIMARY KEY, job_id TEXT REFERENCES jobs(id), batch_id TEXT REFERENCES batches(id),
          stage TEXT NOT NULL, amount REAL NOT NULL, state TEXT NOT NULL,
          basis TEXT NOT NULL DEFAULT 'estimate', created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS spend_job ON spend(job_id);
        CREATE TABLE IF NOT EXISTS cache (
          key TEXT PRIMARY KEY, path TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS requests (
          key TEXT PRIMARY KEY, job_id TEXT REFERENCES jobs(id), provider TEXT NOT NULL,
          data TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS metrics (
          id TEXT PRIMARY KEY, job_id TEXT REFERENCES jobs(id), platform TEXT NOT NULL,
          date TEXT NOT NULL, impressions INTEGER NOT NULL, views INTEGER NOT NULL,
          clicks INTEGER NOT NULL, customers INTEGER NOT NULL,
          revenue REAL NOT NULL, media_spend REAL NOT NULL, created REAL NOT NULL,
          UNIQUE(job_id,platform,date));
        CREATE TABLE IF NOT EXISTS automations (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, spec TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1, interval_hours REAL NOT NULL,
          next_run REAL NOT NULL, last_error TEXT, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS heartbeats (
          id TEXT PRIMARY KEY, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, data TEXT NOT NULL);
        PRAGMA user_version=1;
        ''')
        if not c.execute('SELECT 1 FROM products LIMIT 1').fetchone():
            product = dict(name='The Everyday Bottle', category='Home & lifestyle',
                description='A fictional example product. Replace with your own approved product details.',
                audience='People building a simpler daily routine', price=32, lifetime_orders=1.4,
                contribution_margin=0.5, landing_url='https://example.com/bottle',
                claims=['Reusable stainless steel bottle', 'Twist-off lid', 'Available in three colors'],
                forbidden_claims=['Medical benefits', 'Unverified environmental claims'],
                hooks=['Your everyday essentials, simplified.', 'Meet your next everyday bottle.',
                       'Three colors. One everyday essential.'],
                cta='See the colors and details.', color='#b8f36b', is_example=True)
            c.execute('INSERT INTO products VALUES(?,?,?)', ('example-bottle', json.dumps(product), time.time()))
            for name, voice, color, description in [
                ('Maya', 'af_heart', '#ddb6fe', 'Fictional adult creator in her early 30s, dark wavy hair, warm natural expression, neutral t-shirt, home kitchen, soft window light, candid smartphone portrait, head and shoulders, facing camera'),
                ('Jordan', 'am_michael', '#a6d9f5', 'Fictional adult creator in his mid 30s, short curly hair, casual overshirt, bright living room, candid smartphone portrait, head and shoulders, facing camera'),
                ('Alex', 'af_bella', '#f7bf86', 'Fictional adult creator in her late 20s, short dark hair, casual sweater, home studio, natural light, candid smartphone portrait, head and shoulders, facing camera')]:
                c.execute('INSERT INTO creators VALUES(?,?,?)', (uid('cr_'), json.dumps(dict(name=name,
                    description=description, voice=voice, color=color, reference_asset_id=None,
                    rights='Original fictional synthetic persona', generated=True)), time.time()))


def claim(owner):
    now = time.time()
    with connection(True) as c:
        # A heartbeat extends the lease independently of slow model inference.
        c.execute("UPDATE jobs SET status='queued', owner=NULL, lease=NULL, updated=? WHERE status='running' AND lease<?", (now, now))
        row = c.execute("SELECT * FROM jobs WHERE status='queued' AND available<=? AND cancel_requested=0 ORDER BY created LIMIT 1", (now,)).fetchone()
        if row is None:
            return None
        c.execute("UPDATE jobs SET status='running', attempts=attempts+1, owner=?, lease=?, updated=? WHERE id=?", (owner, now+120, now, row['id']))
        return decode(c.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())
