"""Client for the independent accounting database.

Every delivery is applied in a single transaction: the list header, all entries
and the per-scope active pointer switch together. Repeating a delivery with the
same idempotency key returns the stored receipt instead of posting again.
An advisory lock serialises concurrent writers for the same scope.
"""
from decimal import Decimal
import psycopg2
from sqlalchemy import create_engine,text
from sqlalchemy.exc import SQLAlchemyError
from ..config.settings import LEDGER_DATABASE_URL
class LedgerUnavailable(RuntimeError):pass
class LedgerRejected(RuntimeError):pass
_DDL=(
"""CREATE TABLE IF NOT EXISTS ledger_lists(
 idempotency_key VARCHAR(80) PRIMARY KEY,
 scope_key VARCHAR(160) NOT NULL,
 version BIGINT NOT NULL,
 period VARCHAR(40),
 batch_ref VARCHAR(80) NOT NULL,
 row_count INTEGER NOT NULL,
 total_amount NUMERIC(18,4) NOT NULL,
 state VARCHAR(20) NOT NULL,
 received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(scope_key,version))""",
"""CREATE TABLE IF NOT EXISTS ledger_entries(
 scope_key VARCHAR(160) NOT NULL,
 version BIGINT NOT NULL,
 invoice_id VARCHAR(80) NOT NULL,
 amount NUMERIC(18,4) NOT NULL,
 PRIMARY KEY(scope_key,version,invoice_id),
 FOREIGN KEY(scope_key,version) REFERENCES ledger_lists(scope_key,version) ON DELETE CASCADE)""",
"""CREATE TABLE IF NOT EXISTS ledger_active(
 scope_key VARCHAR(160) PRIMARY KEY,
 version BIGINT NOT NULL,
 idempotency_key VARCHAR(80) NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
)
_engine=None
_schema_ready=False
def engine():
    global _engine
    if not LEDGER_DATABASE_URL:raise LedgerUnavailable('未配置独立账务库连接')
    if _engine is None:
        _engine=create_engine(LEDGER_DATABASE_URL,pool_pre_ping=True,pool_size=5,max_overflow=5,connect_args={'connect_timeout':5})
    return _engine
def ensure_schema():
    """Create the ledger tables in their own transaction; only then mark ready."""
    global _schema_ready
    with engine().begin() as conn:
        for statement in _DDL:conn.execute(text(statement))
    _schema_ready=True
def _ensure():
    if not _schema_ready:ensure_schema()
def _receipt(row):
    return {'state':row['state'],'version':row['version'],'duplicate':True,'row_count':row['row_count'],'total_amount':str(row['total_amount'])}
def deliver(idempotency_key,scope_key,version,period,batch_ref,items):
    """Post a list. Returns the receipt; caller decides active/superseded from state."""
    total=sum((amount for _,amount in items),Decimal('0'))
    _ensure()
    try:
        with engine().begin() as conn:
            conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))'),{'scope':scope_key})
            existing=conn.execute(text('SELECT state,version,row_count,total_amount FROM ledger_lists WHERE idempotency_key=:key'),{'key':idempotency_key}).mappings().first()
            if existing:return _receipt(existing)
            current=conn.execute(text('SELECT version FROM ledger_active WHERE scope_key=:scope'),{'scope':scope_key}).scalar()
            wins=current is None or version>current
            state='active' if wins else 'superseded'
            conn.execute(text('INSERT INTO ledger_lists(idempotency_key,scope_key,version,period,batch_ref,row_count,total_amount,state) VALUES(:key,:scope,:version,:period,:batch_ref,:row_count,:total,:state)'),
                {'key':idempotency_key,'scope':scope_key,'version':version,'period':period,'batch_ref':batch_ref,'row_count':len(items),'total':total,'state':state})
            if items:
                conn.execute(text('INSERT INTO ledger_entries(scope_key,version,invoice_id,amount) VALUES(:scope,:version,:invoice,:amount)'),
                    [{'scope':scope_key,'version':version,'invoice':invoice,'amount':amount} for invoice,amount in items])
            if wins:
                conn.execute(text("UPDATE ledger_lists SET state='superseded' WHERE scope_key=:scope AND state='active' AND version<>:version"),{'scope':scope_key,'version':version})
                conn.execute(text('INSERT INTO ledger_active(scope_key,version,idempotency_key) VALUES(:scope,:version,:key) ON CONFLICT(scope_key) DO UPDATE SET version=EXCLUDED.version,idempotency_key=EXCLUDED.idempotency_key,updated_at=now()'),
                    {'scope':scope_key,'version':version,'key':idempotency_key})
            return {'state':state,'version':version,'duplicate':False,'row_count':len(items),'total_amount':str(total)}
    except SQLAlchemyError as exc:
        # Integrity problems (e.g. the same version with a different key) are business rejections,
        # connection/timeout problems are an outage and must be retried.
        if isinstance(exc.orig,psycopg2.IntegrityError):raise LedgerRejected(str(exc.orig)) from exc
        raise LedgerUnavailable(str(exc)[:300]) from exc
def active_version(scope_key):
    _ensure()
    with engine().begin() as conn:
        return conn.execute(text('SELECT version FROM ledger_active WHERE scope_key=:scope'),{'scope':scope_key}).scalar()
def active_entries(scope_key):
    _ensure()
    with engine().begin() as conn:
        version=conn.execute(text('SELECT version FROM ledger_active WHERE scope_key=:scope'),{'scope':scope_key}).scalar()
        if version is None:return None,[]
        entries=conn.execute(text('SELECT invoice_id,amount FROM ledger_entries WHERE scope_key=:scope AND version=:version ORDER BY invoice_id'),{'scope':scope_key,'version':version}).all()
        return version,entries
def list_versions(scope_key):
    _ensure()
    with engine().begin() as conn:
        return conn.execute(text('SELECT version,idempotency_key,state,row_count,total_amount,period FROM ledger_lists WHERE scope_key=:scope ORDER BY version'),{'scope':scope_key}).mappings().all()

