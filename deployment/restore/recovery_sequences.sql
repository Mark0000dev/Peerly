\set ON_ERROR_STOP on
SET statement_timeout = '30s';
SET lock_timeout = '2s';
BEGIN READ ONLY;
-- A safety guard, not ownership attestation: launcher must own this isolated PG.
SELECT current_database() ~ '^peerly_restore_[0-9a-f]{32}_test$' AS isolated \gset
\if :isolated
\else
\quit 3
\endif
SET LOCAL search_path = pg_catalog;
-- Evaluate identifiers only through format(%I). Never call nextval/setval.
-- Include unowned sequences explicitly: they cannot silently pass a max-ID check.
SELECT format(
 'SELECT jsonb_build_object(''schema'',%L,''name'',%L,''last'',last_value::text,''called'',is_called,''increment'',%L,''minimum'',%L,''maximum'',%L,''cycle'',%L::boolean,''owned'',%L::boolean,''edge'',%s) FROM %I.%I;',
 n.nspname,c.relname,s.seqincrement::text,s.seqmin::text,s.seqmax::text,s.seqcycle,
 a.attname IS NOT NULL,
 CASE WHEN a.attname IS NULL THEN 'NULL' ELSE format(
 '(SELECT %s(%I)::text FROM %I.%I)',
 CASE WHEN s.seqincrement>0 THEN 'max' ELSE 'min' END,a.attname,tn.nspname,t.relname) END,
 n.nspname,c.relname)
FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
LEFT JOIN pg_depend d ON d.classid='pg_class'::regclass AND d.objid=c.oid
 AND d.refclassid='pg_class'::regclass AND d.deptype IN ('a','i')
LEFT JOIN pg_class t ON t.oid=d.refobjid
LEFT JOIN pg_namespace tn ON tn.oid=t.relnamespace
LEFT JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid
WHERE n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
ORDER BY n.nspname,c.relname LIMIT 257
\gexec
ROLLBACK;
