"""Assemble a settlement list from a finished review and deliver it to the ledger.

A batch is eligible only when its review passed and the result carries exactly
one invoice id and one payable amount per row. A page-initiated send writes the
task to a durable outbox; the worker posts it. Therefore a ledger outage never
blocks reviews, and an interrupted send resumes after restart.

Ordering is by batches.review_sequence (the shared acceptance order), not by
arrival time. The ledger switches the active list only if the incoming version
is newer, so a late older list becomes 替代/superseded instead of overwriting.

The idempotency key is stable per batch. If the ledger received a list but the
receipt was lost, the retry is recognised and no entry is posted twice.
"""
import re
from datetime import datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
from sqlalchemy import select
from fastapi import HTTPException
from ..config.settings import LEDGER_MAX_BACKOFF_SECONDS,LEDGER_RETRY_SECONDS
from ..models.batch import Batch
from ..models.delivery import Delivery,DeliveryItem
from ..models.evidence import Evidence
from ..services import ledger
def scope_key(batch):return f'sample:{batch.sample_id}'
def idempotency_key(batch):return f'batch-{batch.id}'
def _cell(row,index):
    if index is None or index>=len(row):return None
    return row[index]
def _period_from_sql(sql):
    match=re.search(r'--\s*(?:账期|period)\s*[:：]\s*([A-Za-z0-9_-]{1,40})',sql or '',re.IGNORECASE)
    return match.group(1) if match else None
def build_list(db,batch):
    """Return (period, items, total) or raise HTTPException with a business reason."""
    if batch.status!='passed':raise HTTPException(409,'仅复核通过的批次可送账')
    evidence=db.scalar(select(Evidence).where(Evidence.batch_id==batch.id))
    if not evidence:raise HTTPException(409,'复核证据尚未生成')
    result=evidence.result or {}
    if result.get('error'):raise HTTPException(409,'复核执行失败，不可送账')
    if not result.get('equivalent'):raise HTTPException(409,'复核结果存在差异，不可送账')
    candidate=result.get('candidate') or {}
    columns=[str(c).lower() for c in (candidate.get('columns') or [])]
    rows=candidate.get('rows') or []
    def index(*names):
        for name in names:
            if name in columns:return columns.index(name)
        return None
    id_at=index('invoice_id')
    amount_at=index('amount')
    if id_at is None or amount_at is None:
        raise HTTPException(409,'清单必须包含唯一账单号（invoice_id）与应付金额（amount）两列')
    if not rows:raise HTTPException(409,'清单为空，不可送账')
    period_at=index('period','billing_period','settlement_period','账期')
    seen=set();items=[];total=Decimal('0')
    for number,row in enumerate(rows,start=1):
        invoice=str(_cell(row,id_at) or '').strip()
        if not invoice:raise HTTPException(409,f'第 {number} 行账单号为空，不可送账')
        if invoice in seen:raise HTTPException(409,f'账单号 {invoice} 在清单中重复，无法确定唯一应付金额')
        raw=_cell(row,amount_at)
        try:amount=Decimal(str(raw))
        except (InvalidOperation,TypeError):raise HTTPException(409,f'账单 {invoice} 的应付金额不是有效数值')
        if not amount.is_finite():raise HTTPException(409,f'账单 {invoice} 的应付金额不是有效数值')
        seen.add(invoice);items.append((invoice,amount));total+=amount
    period=None
    if period_at is not None:
        values={str(_cell(row,period_at) or '').strip() for row in rows}
        if len(values)>1:raise HTTPException(409,'清单内账期不一致，无法整批切换')
        period=values.pop() or None
    return period or _period_from_sql(batch.candidate_sql),items,total
def request_send(db,batch_id,period=None):
    batch=db.get(Batch,batch_id)
    if not batch:raise HTTPException(404,'批次不存在')
    delivery=db.scalar(select(Delivery).where(Delivery.batch_id==batch_id))
    if delivery and delivery.status in ('pending','active','superseded'):
        if period and delivery.status=='pending':
            delivery.period=period;db.commit()
        return serialize(db,delivery,batch)
    if delivery is None:
        computed_period,items,total=build_list(db,batch)
        delivery=Delivery(batch_id=batch.id,period=period or computed_period,scope_key=scope_key(batch),
            version=batch.review_sequence,idempotency_key=idempotency_key(batch),status='pending',
            row_count=len(items),total_amount=total,attempts=0,next_attempt_at=None,
            ledger_received_at=None,last_error=None)
        db.add(delivery);db.flush()
        db.add_all([DeliveryItem(delivery_id=delivery.id,invoice_id=invoice,amount=amount) for invoice,amount in items])
        db.commit()
        return serialize(db,delivery,batch)
    # A terminal failure is retried: clear backoff, keep the same idempotency key.
    delivery.status='pending';delivery.attempts=0;delivery.next_attempt_at=None;delivery.last_error=None
    if period:delivery.period=period
    db.commit()
    return serialize(db,delivery,batch)
def due_deliveries(db,limit=20):
    now=datetime.now(timezone.utc).replace(tzinfo=None)
    return db.scalars(select(Delivery).where(Delivery.status=='pending')
        .where((Delivery.next_attempt_at.is_(None))|(Delivery.next_attempt_at<=now))
        .order_by(Delivery.version).limit(limit)).all()
def _items(db,delivery):
    rows=db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id==delivery.id).order_by(DeliveryItem.invoice_id)).all()
    return [(row.invoice_id,row.amount) for row in rows]
def attempt(db,delivery):
    """One delivery try. Never raises for a ledger outage; returns retry instead."""
    delivery.attempts=(delivery.attempts or 0)+1
    try:
        receipt=ledger.deliver(delivery.idempotency_key,delivery.scope_key,delivery.version,delivery.period,delivery.idempotency_key,_items(db,delivery))
    except ledger.LedgerRejected as exc:
        delivery.status='failed';delivery.last_error=str(exc)[:500];delivery.next_attempt_at=None
        db.commit();return 'rejected'
    except Exception as exc:
        delivery.last_error=str(exc)[:500]
        delay=min(LEDGER_MAX_BACKOFF_SECONDS,LEDGER_RETRY_SECONDS*max(1,2**min(delivery.attempts,6)))
        delivery.next_attempt_at=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(seconds=delay)
        db.commit();return 'retry'
    # The ledger's active pointer is authoritative: a replayed receipt may say "active"
    # even though a newer accepted list has since taken over the scope.
    try:active=ledger.active_version(delivery.scope_key)
    except Exception:active=receipt['version'] if receipt['state']=='active' else None
    delivery.last_error=None;delivery.next_attempt_at=None
    delivery.ledger_received_at=datetime.now(timezone.utc).replace(tzinfo=None)
    if active is not None and delivery.version<active:delivery.status='superseded'
    elif active is not None and delivery.version==active:delivery.status='active'
    else:delivery.status='superseded' if receipt['state']=='superseded' else 'active'
    if delivery.status=='active':
        # Mirror the ledger locally: any older list in this scope is no longer current.
        for other in db.scalars(select(Delivery).where(Delivery.scope_key==delivery.scope_key)
                .where(Delivery.status=='active').where(Delivery.version<delivery.version)).all():
            other.status='superseded'
    db.commit();return 'sent'
def _money(value):return format(Decimal(value),'f')
def serialize(db,delivery,batch=None):
    batch=batch or db.get(Batch,delivery.batch_id)
    return {'id':delivery.id,'batch_id':delivery.batch_id,'batch_name':batch.name if batch else None,
        'scope_key':delivery.scope_key,'version':delivery.version,'period':delivery.period,
        'status':delivery.status,'row_count':delivery.row_count,'total_amount':_money(delivery.total_amount),
        'attempts':delivery.attempts,'last_error':delivery.last_error,
        'next_attempt_at':str(delivery.next_attempt_at) if delivery.next_attempt_at else None,
        'ledger_received_at':str(delivery.ledger_received_at) if delivery.ledger_received_at else None,
        'created_at':str(delivery.created_at)}
def list_deliveries(db):
    rows=db.scalars(select(Delivery).order_by(Delivery.version.desc())).all()
    batches={b.id:b for b in db.scalars(select(Batch).where(Batch.id.in_([r.batch_id for r in rows])))} if rows else {}
    return [serialize(db,row,batches.get(row.batch_id)) for row in rows]
def list_for_batch(db,batch):
    row=db.scalar(select(Delivery).where(Delivery.batch_id==batch.id))
    return serialize(db,row,batch) if row else None
def eligibility(db,batch):
    """Non-raising eligibility summary used by the page."""
    try:
        period,items,total=build_list(db,batch)
        return {'eligible':True,'reason':None,'period':period,'row_count':len(items),'total_amount':_money(total)}
    except HTTPException as exc:
        return {'eligible':False,'reason':exc.detail}
