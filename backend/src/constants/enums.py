ROLES=('admin','operator','viewer')
STATUSES=('queued','running','passed','different','failed')
# Delivery lifecycle: pending covers "waiting for review", "ready to send" and "retrying".
# active / superseded / failed are terminal; a failed batch can be retried and returns to pending.
DELIVERY_STATUSES=('pending','active','superseded','failed')
