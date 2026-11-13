"""Fixed SELECT-only external configuration/destination inspection in owned worker.

Reuse the product's actual configuration-to-target conversion and fingerprint,
without startup, registration, materialization, queue claims or provider sends.
"""

DSN_ADAPTER = """from urllib.parse import unquote_plus,urlsplit,urlunsplit
def connection_options(raw):
 if not raw.startswith(('postgresql+asyncpg://','postgresql://')):
  raise ValueError('probe_database_url_scheme')
 if any(c in raw for c in ('\\r','\\n')):
  raise ValueError('probe_database_url_scheme')
 parts=urlsplit(raw)
 if parts.fragment: raise ValueError('probe_database_url_fragment')
 fields=parts.query.split('&') if parts.query else []
 parsed=[(unquote_plus(v.partition('=')[0]),unquote_plus(v.partition('=')[2])) for v in fields]
 ssl_fields=[i for i,(key,value) in enumerate(parsed) if key.lower()=='ssl']
 options={}
 if ssl_fields:
  if len(ssl_fields)!=1: raise ValueError('probe_ambiguous_ssl_policy')
  index=ssl_fields[0];key,value=parsed[index]
  if key!='ssl' or value!='disable': raise ValueError('probe_unsupported_ssl_policy')
  if any(i!=index and key.lower().startswith('ssl') for i,(key,value) in enumerate(parsed)):
   raise ValueError('probe_ambiguous_ssl_policy')
  fields.pop(index);options['ssl']=False
 options['dsn']=urlunsplit(('postgresql',parts.netloc,parts.path,'&'.join(fields),''))
 return options
"""

EXTERNAL_DATABASE = "\n".join(
    (
        DSN_ADAPTER,
        """import asyncio,json
import asyncpg
from studymate.config import ExternalDeliveryWorkerSettings
from studymate.bootstrap import _external_destination_configs
from studymate.infrastructure.external_delivery.http_adapters.configuration import (
 target_fingerprint)
async def main():
 settings=ExternalDeliveryWorkerSettings()
 configured=sorted(({'sink':c.destination.sink.value,'revision':c.destination.revision,
  'fingerprint':target_fingerprint(c).hex()} for c in _external_destination_configs(settings)),
  key=lambda row:row['sink'])
 c=await asyncpg.connect(
  **connection_options(settings.database_url.get_secret_value()),
  timeout=5,command_timeout=5)
 try:
  async with c.transaction(readonly=True,isolation='repeatable_read'):
   await c.fetchval("SELECT set_config('statement_timeout','5000',true)")
   await c.fetchval("SELECT set_config('lock_timeout','1000',true)")
   readonly=await c.fetchval("SELECT current_setting('transaction_read_only')")
   if readonly!='on': raise RuntimeError('probe_transaction_not_readonly')
   database=await c.fetchval('SELECT current_database()')
   heads=await c.fetch('SELECT version_num FROM public.alembic_version')
   registered=await c.fetch(
    "SELECT sink,revision,encode(fingerprint,'hex') AS fingerprint "
    'FROM public.external_delivery_destinations ORDER BY sink,revision')
   print(json.dumps({'database_name':database,'configured':configured,
    'heads':[row['version_num'] for row in heads],'registered':[dict(row) for row in registered]}))
 finally: await c.close()
asyncio.run(main())
""",
    )
)

EXTERNAL_REGISTRY = "\n".join(
    (
        DSN_ADAPTER,
        """import asyncio,json,os
import asyncpg
async def main():
 c=await asyncpg.connect(
  **connection_options(os.environ['DATABASE_URL']),
  timeout=5,command_timeout=5)
 try:
  async with c.transaction(readonly=True,isolation='repeatable_read'):
   await c.fetchval("SELECT set_config('statement_timeout','5000',true)")
   await c.fetchval("SELECT set_config('lock_timeout','1000',true)")
   readonly=await c.fetchval("SELECT current_setting('transaction_read_only')")
   if readonly!='on': raise RuntimeError('probe_transaction_not_readonly')
   database=await c.fetchval('SELECT current_database()')
   heads=await c.fetch('SELECT version_num FROM public.alembic_version')
   registered=await c.fetch(
    "SELECT sink,revision,encode(fingerprint,'hex') AS fingerprint "
    'FROM public.external_delivery_destinations ORDER BY sink,revision')
   print(json.dumps({'database_name':database,
    'heads':[row['version_num'] for row in heads],'registered':[dict(row) for row in registered]}))
 finally: await c.close()
asyncio.run(main())
""",
    )
)
