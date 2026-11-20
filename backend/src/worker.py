import json,os,time,traceback
from pathlib import Path
from sqlalchemy import select
from .config.database import Session
from .models.batch import Batch
from .models.delivery import Delivery
from .models.evidence import Evidence
from .models.sample import Sample
from .services import delivery as deliveries
from .services.batch import queue
from .services.query_engine import compare
ARTIFACTS=Path(os.getenv('ARTIFACTS_DIR','/artifacts'))
def run_one(batch_id):
    """Execute one review and persist evidence. Never opens a ledger connection."""
    with Session() as db:
        batch=db.get(Batch,batch_id)
        if not batch or db.scalar(select(Evidence).where(Evidence.batch_id==batch_id)):return
        sample=db.get(Sample,batch.sample_id);batch.status='running';db.commit()
        try:
            result=compare(sample.original_sql,batch.candidate_sql)
            batch.status='passed' if result['equivalent'] else 'different'
        except Exception as exc:
            result={'error':str(exc)[:500]};batch.status='failed'
        db.add(Evidence(batch_id=batch_id,result=result));db.commit()
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
        (ARTIFACTS/f'review-{batch_id}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
def send_due():
    """Post outbox tasks whose retry time has arrived. A ledger outage leaves them pending."""
    with Session() as db:
        ids=[row.id for row in deliveries.due_deliveries(db)]
    for ident in ids:
        with Session() as db:
            row=db.get(Delivery,ident)
            if row and row.status=='pending':
                try:deliveries.attempt(db,row)
                except Exception:traceback.print_exc();db.rollback()
def main():
    while True:
        try:
            ARTIFACTS.mkdir(parents=True,exist_ok=True)
            (ARTIFACTS/'worker.heartbeat').write_text(str(time.time()))
            item=queue.blpop('query-review:jobs',timeout=2)
            if item:run_one(int(item[1]))
            else:
                with Session() as db:pending=list(db.scalars(select(Batch.id).where(Batch.status.in_(['queued','running']))))
                for ident in pending:run_one(ident)
            send_due()
        except Exception:traceback.print_exc();time.sleep(2)
if __name__=='__main__':main()
