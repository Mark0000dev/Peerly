# Recovery catalog format 3

Install `recovery_and.py` with `recovery_checks.py`, `recovery_catalog.sql` and
`capture_backup.py`. Keep installed modules/SQL immutable to the runtime account.
Update the capture-module pin and deploy the matched SQL pin together. Existing
row/media baseline format remains 1; this changes only the recovery catalog format.

PostgreSQL 16 logical restore can flatten nested AND groups in CHECK definitions.
Format 3 adds only this associative regrouping to format 2's literal-array cast
handling. The canonicalizer preserves ordered operands, OR/NOT boundaries, quoted
strings/identifiers, types, casts and operators. It only removes a directly nested
AND operand's grouping when its parent is itself an AND group. It does not sort,
deduplicate, simplify predicates, reorder evaluation or evaluate SQL/functions.
It is not a generic SQL normalizer or a tolerance rule for changed constraints.

CASE, BETWEEN, SELECT/WITH/UNION/EXISTS and window-expression tokens are left exact.
Quoted occurrences of these words remain quoted tokens. Incomplete groups reject;
nesting is bounded to 64. Unsupported forms may still produce a conservative
mismatch and require investigation. Raw native definition SHA256 is verified
before token canonicalization. Changed operands, mixed OR/NOT, types or values must
not be treated as equivalent.

The SQL emits format 3 and the checker rejects format 2. Existing completed capture
files/receipts must remain unchanged. A later live source catalog cannot supply a
missing historical snapshot. Any migration of historical metadata needs separate,
explicit evidence with exact input/output hashes and provenance; it is not a new
native source capture and must not inherit the old capture's completion claim.
No helper automatically upgrades an archive, repairs a sequence, changes a source
schema or enables application recovery. Full recovery acceptance remains separate.
