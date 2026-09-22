---
name: sql-review
description: "Review SQL joins, aggregations, NULL semantics and query plans without changing production databases. SQL 쿼리 조인 집계 검토."
---

# SQL review

Confirm the SQL dialect and the intended row grain. Inspect keys, uniqueness assumptions, and NULL behavior before suggesting changes.
Trace whether joins multiply rows before aggregation. Prefer a tiny, explicitly synthetic example to test suspected duplicates.
Use EXPLAIN without ANALYZE for a read-only first look where the database supports it; ANALYZE may execute the statement.
Never issue production writes or schema changes without the user's authorization. State assumptions when schema or execution plans are unavailable.
Return a corrected query, the reason it changes results or performance, and a read-only verification query.
