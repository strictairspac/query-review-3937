Schema version 2: SQLAlchemy metadata creates users/samples/batches/evidence/audit/deliveries/delivery_items. seed_demo initializes the separate invoices fixture table and NOLOGIN query_reader. invoices is the only permitted SQL source. Run `python -m scripts.seed_demo` for repeatable initialization; natural keys preserve user edits.

Version 2 adds the delivery outbox. `ensure_schema()` runs on backend start and seed:
- creates `deliveries` and `delivery_items` if missing;
- adds `batches.review_sequence` (BIGINT, unique) to a v1 table in place, backfilling legacy rows in id order and then advancing the backing sequence. `review_sequence` is the single acceptance order used to decide which settlement list is newest; it is assigned when the review request is accepted, so concurrent accepts and late deliveries stay consistent.

The independent ledger database owns its own schema (`ledger_lists`, `ledger_entries`, `ledger_active`). The backend creates those tables on first delivery so both databases stay independently deployable.
