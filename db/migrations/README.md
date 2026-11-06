# Database migrations

Additive schema changes are applied at startup by `db/migrate.py` (idempotent `ALTER TABLE`).

The `schema_version` table tracks the applied migration generation. Fresh databases get the full DDL from `db/schema.sql` first, then any pending column additions.

Future versioned SQL files can be added here as `NNN_description.sql` and registered in `migrate.py`.
