from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import BigInteger,String,Text,ForeignKey,DateTime,func,text
from datetime import datetime
from ..config.database import Base
REVIEW_SEQUENCE='batches_review_sequence_seq'
class Batch(Base):
    __tablename__='batches'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(120),unique=True)
    sample_id:Mapped[int]=mapped_column(ForeignKey('samples.id'))
    candidate_sql:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(20),default='queued')
    # Assigned by PostgreSQL when the review request is accepted. This gives every
    # process one shared total order, which is what decides "newest review wins"
    # for ledger switching (wall-clock timestamps can tie or move backwards).
    review_sequence:Mapped[int]=mapped_column(BigInteger,nullable=False,server_default=text(f"nextval('{REVIEW_SEQUENCE}')"))
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
