from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import BigInteger,ForeignKey,Integer,Numeric,String,Text,DateTime,UniqueConstraint,func
from ..config.database import Base
class Delivery(Base):
    __tablename__='deliveries'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('batches.id'),unique=True)
    period:Mapped[str|None]=mapped_column(String(40),nullable=True)
    scope_key:Mapped[str]=mapped_column(String(160))
    version:Mapped[int]=mapped_column(BigInteger)
    idempotency_key:Mapped[str]=mapped_column(String(80),unique=True)
    status:Mapped[str]=mapped_column(String(20),default='pending',index=True)
    row_count:Mapped[int]=mapped_column(Integer,default=0)
    total_amount:Mapped[Decimal]=mapped_column(Numeric(18,4),default=0)
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    last_error:Mapped[str|None]=mapped_column(Text,nullable=True)
    next_attempt_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    ledger_received_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now(),onupdate=func.now())
class DeliveryItem(Base):
    __tablename__='delivery_items'
    __table_args__=(UniqueConstraint('delivery_id','invoice_id',name='uq_delivery_item'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    delivery_id:Mapped[int]=mapped_column(ForeignKey('deliveries.id'))
    invoice_id:Mapped[str]=mapped_column(String(80))
    amount:Mapped[Decimal]=mapped_column(Numeric(18,4))
