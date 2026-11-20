"""Durable publication reservations. Remote delivery is not live publication."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS publications (
        article_id TEXT PRIMARY KEY, quota_day TEXT NOT NULL, status TEXT NOT NULL,
        reserved_at TEXT NOT NULL, receipt TEXT, published_at TEXT)''')
    db.commit()


def reserve(db, article_id, target, zone, now=None):
    if type(target) is not int or target < 0:
        raise ValueError("Daily target must be a nonnegative integer")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    day = now.astimezone(ZoneInfo(zone)).date().isoformat()
    db.execute("BEGIN IMMEDIATE")
    try:
        existing = db.execute("SELECT status FROM publications WHERE article_id=?", (article_id,)).fetchone()
        if existing and existing[0] != 'failed':
            db.commit()
            return False, 'already_' + existing[0]
        used = db.execute("SELECT COUNT(*) FROM publications WHERE quota_day=? AND status IN ('reserved','delivered','published')", (day,)).fetchone()[0]
        if used >= target:
            db.commit()
            return False, 'daily_quota_reached'
        db.execute("INSERT INTO publications(article_id,quota_day,status,reserved_at) VALUES (?,?,'reserved',?) ON CONFLICT(article_id) DO UPDATE SET quota_day=excluded.quota_day,status='reserved',reserved_at=excluded.reserved_at,receipt=NULL,published_at=NULL",
                   (article_id, day, now.isoformat()))
        db.commit()
        return True, 'reserved'
    except BaseException:
        db.rollback()
        raise


def record_delivery(db, article_id, receipt):
    if not isinstance(receipt, str) or not receipt.strip():
        raise ValueError("Remote commit or PR receipt required")
    cursor = db.execute("UPDATE publications SET status='delivered',receipt=? WHERE article_id=? AND status='reserved'", (receipt, article_id))
    if cursor.rowcount != 1:
        raise ValueError("Article is not reserved")
    db.commit()


def confirm_publication(db, article_id, verified, now=None):
    if verified is not True:
        raise ValueError("Live publication verification required")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    cursor = db.execute("UPDATE publications SET status='published',published_at=? WHERE article_id=? AND status='delivered'", (now.isoformat(), article_id))
    if cursor.rowcount != 1:
        raise ValueError("Article has no remote delivery receipt")
    db.commit()


def release_failed(db, article_id, confirmed_no_remote_write):
    # A timeout may hide a successful remote commit; never release automatically.
    if confirmed_no_remote_write is not True:
        raise ValueError("Reconcile remote state before releasing a reservation")
    cursor = db.execute("UPDATE publications SET status='failed' WHERE article_id=? AND status='reserved'", (article_id,))
    if cursor.rowcount != 1:
        raise ValueError("Only undelivered reservations can be released")
    db.commit()
