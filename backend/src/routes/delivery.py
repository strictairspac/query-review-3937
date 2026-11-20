from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from ..config.database import get_db
from ..models.delivery import Delivery,DeliveryItem
from ..services.auth import current_user
from ..services import delivery as deliveries
router=APIRouter(prefix='/deliveries')
@router.get('')
def listing(db=Depends(get_db),user=Depends(current_user)):return deliveries.list_deliveries(db)
@router.get('/{delivery_id}')
def detail(delivery_id:int,db=Depends(get_db),user=Depends(current_user)):
    row=db.get(Delivery,delivery_id)
    if not row:raise HTTPException(404,'送账任务不存在')
    data=deliveries.serialize(db,row)
    items=db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id==delivery_id).order_by(DeliveryItem.invoice_id).limit(20)).all()
    data['items']=[{'invoice_id':item.invoice_id,'amount':str(item.amount)} for item in items]
    data['items_truncated']=len(items)<row.row_count
    return data
