import time
from datetime import datetime
from zoneinfo import ZoneInfo
from . import config, db


class BudgetExceeded(RuntimeError):
    pass


def day_start():
    import os
    now = datetime.now(ZoneInfo(os.getenv('UGC_TIMEZONE', 'America/Indiana/Indianapolis')))
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def reserve(job, stage, amount, key=None):
    """Atomic reservations prevent concurrent jobs from oversubscribing caps.

    These are conservative provider-cost estimates, not invoice enforcement.
    Unknown outcomes retain their reservation until reconciliation.
    """
    amount = round(max(0, amount), 6)
    sid = 'cost_' + key if key else db.uid('cost_')
    with db.connection(True) as c:
        if c.execute('SELECT 1 FROM spend WHERE id=?', (sid,)).fetchone():
            return sid
        batch = c.execute('SELECT budget FROM batches WHERE id=?', (job['batch_id'],)).fetchone()
        used = c.execute("SELECT COALESCE(SUM(amount),0) FROM spend WHERE batch_id=? AND state!='released'", (job['batch_id'],)).fetchone()[0]
        daily = c.execute("SELECT COALESCE(SUM(amount),0) FROM spend WHERE created>=? AND state!='released'", (day_start(),)).fetchone()[0]
        if used + amount > batch['budget'] + 1e-7:
            raise BudgetExceeded(f'Batch cap reached. ${used:.2f} committed; next step reserves ${amount:.2f}. Increase the batch cap to continue.')
        if daily + amount > config.DAILY_BUDGET + 1e-7:
            raise BudgetExceeded(f'Daily cap reached (${config.DAILY_BUDGET:.2f}). Resume after reset or update UGC_DAILY_BUDGET.')
        c.execute('INSERT INTO spend VALUES(?,?,?,?,?,?,?,?)',
            (sid, job['id'], job['batch_id'], stage, amount, 'reserved', 'estimate', time.time()))
    return sid


def settle(sid, amount=None, basis='estimate'):
    # An actual cost above reservation is recorded honestly, even over a cap.
    if amount is None:
        db.execute("UPDATE spend SET state='committed',basis=? WHERE id=?", (basis, sid))
    else:
        db.execute("UPDATE spend SET state='committed',amount=?,basis=? WHERE id=?", (round(amount, 6), basis, sid))


def summary():
    return db.one("SELECT COALESCE(SUM(amount),0) AS total, COALESCE(SUM(CASE WHEN created>=? THEN amount ELSE 0 END),0) AS today, COALESCE(SUM(CASE WHEN state='reserved' THEN amount ELSE 0 END),0) AS reserved FROM spend WHERE state!='released'", (day_start(),))
