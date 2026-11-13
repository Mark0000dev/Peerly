"""Fixed SELECT-only external configuration/destination inspection in owned worker.

Reuse the product's actual configuration-to-target conversion and fingerprint,
without startup, registration, materialization, queue claims or provider sends.
"""

EXTERNAL_DATABASE = """import asyncio,json
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
  settings.database_url.get_secret_value().replace('postgresql+asyncpg://','postgresql://',1),
  timeout=5,command_timeout=5,server_settings={
   'default_transaction_read_only':'on','statement_timeout':'5000','lock_timeout':'1000'})
 try:
  async with c.transaction(readonly=True,isolation='repeatable_read'):
   database=await c.fetchval('SELECT current_database()')
   heads=await c.fetch('SELECT version_num FROM public.alembic_version')
   registered=await c.fetch(
    "SELECT sink,revision,encode(fingerprint,'hex') AS fingerprint "
    'FROM public.external_delivery_destinations ORDER BY sink,revision')
   print(json.dumps({'database_name':database,'configured':configured,
    'heads':[row['version_num'] for row in heads],'registered':[dict(row) for row in registered]}))
 finally: await c.close()
asyncio.run(main())
"""

EXTERNAL_REGISTRY = """import asyncio,json,os
import asyncpg
async def main():
 c=await asyncpg.connect(
  os.environ['DATABASE_URL'].replace('postgresql+asyncpg://','postgresql://',1),
  timeout=5,command_timeout=5,server_settings={
   'default_transaction_read_only':'on','statement_timeout':'5000','lock_timeout':'1000'})
 try:
  async with c.transaction(readonly=True,isolation='repeatable_read'):
   database=await c.fetchval('SELECT current_database()')
   heads=await c.fetch('SELECT version_num FROM public.alembic_version')
   registered=await c.fetch(
    "SELECT sink,revision,encode(fingerprint,'hex') AS fingerprint "
    'FROM public.external_delivery_destinations ORDER BY sink,revision')
   print(json.dumps({'database_name':database,
    'heads':[row['version_num'] for row in heads],'registered':[dict(row) for row in registered]}))
 finally: await c.close()
asyncio.run(main())
"""
