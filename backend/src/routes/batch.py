from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..models.batch import Batch
from ..schemas.batch import BatchInput,SendInput
from ..services.auth import current_user,writer
from ..services.batch import list_batches,create_batch
from ..services import delivery as deliveries
router=APIRouter(prefix='/batches')
@router.get('')
def listing(db=Depends(get_db),user=Depends(current_user)):return list_batches(db)
@router.post('',status_code=202)
def create(data:BatchInput,db=Depends(get_db),user=Depends(writer)):return create_batch(db,data)
@router.get('/{batch_id}/delivery')
def delivery_status(batch_id:int,db=Depends(get_db),user=Depends(current_user)):
    batch=db.get(Batch,batch_id)
    if not batch:return {'batch_id':batch_id,'status':None,'eligible':False,'reason':'批次不存在'}
    delivery=deliveries.list_for_batch(db,batch)
    return {'batch_id':batch_id,**deliveries.eligibility(db,batch),'delivery':delivery}
@router.post('/{batch_id}/delivery',status_code=202)
def send(batch_id:int,data:SendInput|None=None,db=Depends(get_db),user=Depends(writer)):
    return deliveries.request_send(db,batch_id,period=(data.period if data else None))
