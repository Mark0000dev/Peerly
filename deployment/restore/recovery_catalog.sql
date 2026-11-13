\set ON_ERROR_STOP on
SET statement_timeout = '30s';
SET lock_timeout = '2s';
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
\if :{?backup_snapshot}
SET TRANSACTION SNAPSHOT :'backup_snapshot';
\endif
SET LOCAL search_path = pg_catalog;
-- Definitions are hashed in-server; no routine bodies/default literals leave PG.
WITH namespaces AS (
 SELECT oid, nspname FROM pg_namespace
 WHERE nspname <> 'information_schema' AND nspname !~ '^pg_'
), entries AS (
 SELECT 'schema' AS kind, n.nspname AS schema, '' AS name, '' AS detail
 FROM namespaces n
 UNION ALL
 SELECT 'column', n.nspname, c.relname || '.' || a.attname,
 concat_ws('|', c.relkind, a.attnum, format_type(a.atttypid,a.atttypmod),
 a.attnotnull, a.attidentity, a.attgenerated,
 coalesce(pg_get_expr(d.adbin,d.adrelid),''), coalesce(coll.collname,''))
 FROM pg_class c JOIN namespaces n ON n.oid=c.relnamespace
 JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
 LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
 LEFT JOIN pg_collation coll ON coll.oid=a.attcollation
 WHERE c.relkind IN ('r','p','v','m','f')
 UNION ALL
 SELECT 'relation', n.nspname, c.relname,
 concat_ws('|', c.relkind,c.relpersistence,c.relrowsecurity,c.relforcerowsecurity,
 coalesce(array_to_string(c.reloptions,','),''),
 CASE WHEN c.relkind IN ('v','m') THEN pg_get_viewdef(c.oid,false) ELSE '' END,
 coalesce(pg_get_partkeydef(c.oid),''),
 coalesce(pg_get_expr(c.relpartbound,c.oid),''))
 FROM pg_class c JOIN namespaces n ON n.oid=c.relnamespace
 WHERE c.relkind IN ('r','p','v','m','f')
 UNION ALL
 SELECT 'constraint', n.nspname, c.relname || '.' || x.conname,
 concat_ws('|',x.contype,x.convalidated,pg_get_constraintdef(x.oid,false))
 FROM pg_constraint x JOIN namespaces n ON n.oid=x.connamespace
 JOIN pg_class c ON c.oid=x.conrelid
 UNION ALL
 SELECT 'index', n.nspname, c.relname,
 concat_ws('|',pg_get_indexdef(i.indexrelid),i.indisvalid,i.indisready,i.indislive)
 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
 JOIN namespaces n ON n.oid=c.relnamespace
 UNION ALL
 SELECT 'trigger', n.nspname, c.relname || '.' || t.tgname,
 concat_ws('|', t.tgenabled,pg_get_triggerdef(t.oid,false))
 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
 JOIN namespaces n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal
 UNION ALL
 SELECT 'routine',n.nspname,p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')',
 pg_get_functiondef(p.oid)
 FROM pg_proc p JOIN namespaces n ON n.oid=p.pronamespace WHERE p.prokind IN ('f','p')
 UNION ALL
 SELECT 'enum',n.nspname,t.typname,
 string_agg(e.enumlabel,'|' ORDER BY e.enumsortorder)
 FROM pg_type t JOIN namespaces n ON n.oid=t.typnamespace
 JOIN pg_enum e ON e.enumtypid=t.oid GROUP BY n.nspname,t.typname
 UNION ALL
 SELECT 'sequence',n.nspname,c.relname,
 concat_ws('|',format_type(s.seqtypid,NULL),s.seqstart,s.seqincrement,
 s.seqmax,s.seqmin,s.seqcache,s.seqcycle,tn.nspname,t.relname,a.attname)
 FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid
 JOIN namespaces n ON n.oid=c.relnamespace
 LEFT JOIN pg_depend d ON d.classid='pg_class'::regclass AND d.objid=c.oid
 AND d.refclassid='pg_class'::regclass AND d.deptype IN ('a','i')
 LEFT JOIN pg_class t ON t.oid=d.refobjid
 LEFT JOIN pg_namespace tn ON tn.oid=t.relnamespace
 LEFT JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid
), bounded AS (SELECT * FROM entries ORDER BY kind,schema,name LIMIT 20001)
SELECT jsonb_build_object(
 'format',3,'database',current_database(),
 'heads',(SELECT jsonb_agg(version_num ORDER BY version_num) FROM public.alembic_version),
 'entries',(SELECT coalesce(jsonb_agg(jsonb_build_object('kind',kind,'schema',schema,
 'name',name,'sha256',encode(sha256(convert_to(detail,'UTF8')),'hex'),
 'definition',CASE WHEN kind IN ('constraint','index') THEN detail ELSE NULL END)
 ORDER BY kind,schema,name),'[]'::jsonb) FROM bounded),
 'invalid_indexes',(SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
 JOIN namespaces n ON n.oid=c.relnamespace WHERE NOT i.indisvalid OR NOT i.indisready OR NOT i.indislive)
);
ROLLBACK;
