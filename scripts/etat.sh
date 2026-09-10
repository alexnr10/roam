#!/usr/bin/env sh
#
# Où en est ce clone ? Une réponse en cinq lignes.
#
# À lancer AVANT toute série de commandes. Deux fois déjà, une commande a
# échoué non pas parce qu'elle était fausse, mais parce que le clone était
# ailleurs qu'on ne le croyait : une branche restée en arrière, un `main` local
# qui n'avait jamais bougé depuis le premier commit. Ni l'un ni l'autre ne se
# signale — `git pull` répond « Already up to date » sur la branche courante,
# même quand il vient de télécharger cent commits pour une autre.
#
#     sh scripts/etat.sh
#
set -e
cd "$(dirname "$0")/.."

printf 'Récupération des références… '
git fetch --quiet origin 2>/dev/null || printf '(réseau indisponible) '
printf '\n\n'

branche=$(git rev-parse --abbrev-ref HEAD)
tete=$(git rev-parse --short HEAD)
sujet=$(git log -1 --pretty=%s)

printf '  branche   %s\n' "$branche"
printf '  commit    %s  %s\n' "$tete" "$sujet"

amont=$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)
if [ -z "$amont" ]; then
  printf '  amont     aucun — cette branche ne suit rien\n'
else
  compte=$(git rev-list --left-right --count "$amont"...HEAD)
  retard=$(printf '%s' "$compte" | cut -f1)
  avance=$(printf '%s' "$compte" | cut -f2)
  printf '  amont     %s' "$amont"
  [ "$retard" -gt 0 ] && printf ' — %s commit(s) DE RETARD' "$retard"
  [ "$avance" -gt 0 ] && printf ' — %s commit(s) d’avance' "$avance"
  [ "$retard" -eq 0 ] && [ "$avance" -eq 0 ] && printf ' — à jour'
  printf '\n'
fi

sales=$(git status --porcelain | wc -l | tr -d ' ')
if [ "$sales" -eq 0 ]; then
  printf '  travail   propre\n'
else
  printf '  travail   %s fichier(s) modifié(s) :\n' "$sales"
  git status --porcelain | head -8 | sed 's/^/              /'
fi

printf '\n'
if [ -n "$amont" ] && [ "${retard:-0}" -gt 0 ]; then
  printf '  → `git pull` avant de continuer.\n'
elif [ "$sales" -gt 0 ]; then
  printf '  → des modifications locales : les committer ou les ranger avant de changer de branche.\n'
else
  printf '  → prêt.\n'
fi
