"""Fixed read-only container probes; no bootstrap, consumption or writes."""

BASE = """import asyncio,json,os
import asyncpg
async def snapshot():
 c=await asyncpg.connect(
  os.environ['DATABASE_URL'].replace('postgresql+asyncpg://','postgresql://',1),
  timeout=5,command_timeout=5,server_settings={
   'default_transaction_read_only':'on','statement_timeout':'5000','lock_timeout':'1000'})
 try:
  async with c.transaction(readonly=True):
   database=await c.fetchval('SELECT current_database()')
   heads=await c.fetch('SELECT version_num FROM public.alembic_version')
   slot=await c.fetchrow(
    'SELECT runtime_worker_id::text AS worker_id,runtime_started_at::text AS started_at,'
    'runtime_model,runtime_prompt,runtime_schema,runtime_adapter,runtime_report_guard_version,'
    "(runtime_state='ready' AND runtime_heartbeat_at<=clock_timestamp() "
    'AND clock_timestamp()<runtime_valid_until) AS fresh '
    'FROM public.ai_executor_slot WHERE id=1')
   return {'database_name':database,'heads':[r['version_num'] for r in heads],
    'ai_slot':dict(slot) if slot else {}}
 finally: await c.close()
"""
DATABASE = (
    BASE
    + """from studymate.config import Settings
async def main():
 result=await snapshot()
 result['approved_releases']=[r.model_dump(mode='json') for r in Settings().public_asset_releases]
 print(json.dumps(result))
asyncio.run(main())
"""
)
SAFETY_DATABASE = (
    BASE
    + """async def main():
 print(json.dumps(await snapshot()))
asyncio.run(main())
"""
)
