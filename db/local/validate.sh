#!/usr/bin/env bash
# Valide db/schema.sql et un seed généré sur un PostgreSQL + PostGIS local.
#
#   ./db/local/validate.sh [chemin/vers/seed.sql]
#
# Charge d'abord les bouchons Supabase (auth.uid()), puis le schéma, puis le seed —
# deux fois, pour vérifier l'idempotence du seed.

set -euo pipefail

SEED="${1:-pipeline/data/out/seed.sql}"
DB="${ROAM_TEST_DB:-roam_validate}"
PSQL=(psql -v ON_ERROR_STOP=1 -q -d "$DB")

dropdb --if-exists "$DB"
createdb "$DB"

"${PSQL[@]}" -f db/local/supabase_stubs.sql
"${PSQL[@]}" -f db/schema.sql
echo "schéma chargé"

if [[ -f "$SEED" ]]; then
  "${PSQL[@]}" -f "$SEED"
  "${PSQL[@]}" -f "$SEED"   # un seed doit pouvoir se rejouer sans rien casser
  echo "seed chargé deux fois (idempotent)"
  psql -d "$DB" -c "select
    (select count(*) from places)            as lieux,
    (select count(*) from collections)       as collections,
    (select count(*) from collection_places) as appartenances;"
else
  echo "pas de seed à $SEED — schéma seul validé"
fi
