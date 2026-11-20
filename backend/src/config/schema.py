"""Schema creation and in-place upgrades (schema v2)."""
from sqlalchemy import text
from .database import Base,engine
from ..models.batch import REVIEW_SEQUENCE
def ensure_schema():
    # Import models so every table is registered on Base.metadata.
    from ..models import audit,batch,delivery,evidence,sample,user  # noqa: F401
    # The sequence must exist before create_all emits batches.review_sequence.
    with engine.begin() as conn:conn.execute(text(f'CREATE SEQUENCE IF NOT EXISTS {REVIEW_SEQUENCE}'))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # Upgrades an existing v1 batches table in place; a no-op when fresh.
        conn.execute(text('ALTER TABLE batches ADD COLUMN IF NOT EXISTS review_sequence BIGINT'))
        conn.execute(text(f"ALTER TABLE batches ALTER COLUMN review_sequence SET DEFAULT nextval('{REVIEW_SEQUENCE}')"))
        # Legacy rows are ordered by id, which was their acceptance order in v1.
        conn.execute(text(f"""UPDATE batches b SET review_sequence=s.value
            FROM (SELECT id,nextval('{REVIEW_SEQUENCE}') AS value FROM
                  (SELECT id FROM batches WHERE review_sequence IS NULL ORDER BY id) ordered) s
            WHERE b.id=s.id"""))
        conn.execute(text('ALTER TABLE batches ALTER COLUMN review_sequence SET NOT NULL'))
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ux_batches_review_sequence ON batches(review_sequence)'))
        # Advance the sequence past any backfilled value without moving it backwards
        # when another process has already allocated higher values.
        conn.execute(text(f"""DO $$
            DECLARE backfilled bigint;
            BEGIN
                SELECT MAX(review_sequence) INTO backfilled FROM batches;
                IF backfilled IS NULL THEN
                    PERFORM setval('{REVIEW_SEQUENCE}',1,false);
                ELSIF (SELECT last_value FROM {REVIEW_SEQUENCE})<backfilled THEN
                    PERFORM setval('{REVIEW_SEQUENCE}',backfilled,true);
                END IF;
            END $$"""))
