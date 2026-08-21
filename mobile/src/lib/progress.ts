import type { Collection, Tier, Visit } from '../types';

/**
 * Progression, niveaux et badges.
 *
 * Une visite déclarée compte dans le pourcentage ; seule une visite vérifiée au
 * GPS ouvre les badges marqués « vérifié ». C'est le compromis qui permet de
 * remplir sa carte à l'inscription sans vider le jeu de son sens.
 */

export const BADGE_THRESHOLDS = [25, 50, 75, 100] as const;

export type TierProgress = {
  tier: Tier;
  visited: number;
  total: number;
  /** Un niveau est verrouillé tant que le précédent n'est pas terminé. */
  unlocked: boolean;
  complete: boolean;
};

export type CollectionProgress = {
  slug: string;
  visited: number;
  verified: number;
  total: number;
  pct: number;
  tiers: TierProgress[];
  /** Niveau courant : le plus haut niveau débloqué. */
  currentTier: Tier;
  complete: boolean;
};

export function visitedIds(visits: Visit[]): Set<string> {
  return new Set(visits.map((visit) => visit.placeId));
}

export function computeProgress(
  collection: Collection,
  visits: Visit[],
): CollectionProgress {
  const byPlace = new Map(visits.map((visit) => [visit.placeId, visit]));

  const perTier = [1, 2, 3].map((tier) => {
    const members = collection.places.filter((member) => member.tier === tier);
    const visited = members.filter((member) => byPlace.has(member.placeId)).length;
    return { tier: tier as Tier, visited, total: members.length };
  });

  const tiers: TierProgress[] = [];
  let previousComplete = true;
  for (const entry of perTier) {
    const complete = entry.total > 0 && entry.visited === entry.total;
    tiers.push({
      ...entry,
      // Un niveau vide ne bloque pas le suivant.
      unlocked: previousComplete,
      complete,
    });
    previousComplete = previousComplete && (complete || entry.total === 0);
  }

  const visited = collection.places.filter((member) =>
    byPlace.has(member.placeId),
  ).length;
  const verified = collection.places.filter(
    (member) => byPlace.get(member.placeId)?.verified,
  ).length;
  const total = collection.places.length;

  const currentTier = (tiers.filter((tier) => tier.unlocked).length || 1) as Tier;

  return {
    slug: collection.slug,
    visited,
    verified,
    total,
    pct: total === 0 ? 0 : Math.round((visited / total) * 1000) / 10,
    tiers,
    currentTier: Math.min(currentTier, 3) as Tier,
    complete: total > 0 && visited === total,
  };
}

export type Badge = {
  id: string;
  collectionSlug: string;
  collectionName: string;
  label: string;
  kind: 'threshold' | 'tier';
  value: number;
  /** Exige des visites vérifiées au GPS. */
  requiresVerified: boolean;
};

/** Badges obtenus sur une collection. */
export function earnedBadges(
  collection: Collection,
  progress: CollectionProgress,
): Badge[] {
  const badges: Badge[] = [];

  for (const threshold of BADGE_THRESHOLDS) {
    if (progress.pct >= threshold) {
      badges.push({
        id: `${collection.slug}:pct:${threshold}`,
        collectionSlug: collection.slug,
        collectionName: collection.name,
        label: threshold === 100 ? 'Collection complète' : `${threshold} %`,
        kind: 'threshold',
        value: threshold,
        requiresVerified: false,
      });
    }
  }

  for (const tier of progress.tiers) {
    if (tier.complete) {
      badges.push({
        id: `${collection.slug}:tier:${tier.tier}`,
        collectionSlug: collection.slug,
        collectionName: collection.name,
        label: `Niveau ${tier.tier} terminé`,
        kind: 'tier',
        value: tier.tier,
        requiresVerified: false,
      });
    }
  }

  return badges;
}

/** Prochain palier à atteindre, pour donner un objectif lisible. */
export function nextMilestone(
  progress: CollectionProgress,
): { label: string; remaining: number } | null {
  const activeTier = progress.tiers.find(
    (tier) => tier.unlocked && !tier.complete && tier.total > 0,
  );
  if (activeTier) {
    return {
      label: `Niveau ${activeTier.tier}`,
      remaining: activeTier.total - activeTier.visited,
    };
  }

  const threshold = BADGE_THRESHOLDS.find((value) => progress.pct < value);
  if (threshold === undefined) return null;

  const needed = Math.ceil((threshold / 100) * progress.total) - progress.visited;
  return { label: `${threshold} %`, remaining: Math.max(needed, 1) };
}
