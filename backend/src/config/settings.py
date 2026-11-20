import os
DATABASE_URL=os.environ['DATABASE_URL']
REDIS_URL=os.getenv('REDIS_URL','redis://redis:6379/0')
JWT_SECRET=os.environ['JWT_SECRET']
# Independent accounting database. Empty means the ledger link is not configured.
LEDGER_DATABASE_URL=os.getenv('LEDGER_DATABASE_URL','')
LEDGER_RETRY_SECONDS=int(os.getenv('LEDGER_RETRY_SECONDS','5'))
LEDGER_MAX_BACKOFF_SECONDS=int(os.getenv('LEDGER_MAX_BACKOFF_SECONDS','60'))
