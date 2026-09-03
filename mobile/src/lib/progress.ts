import type { Collection, Place, Tier, Visit } from '../types';

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

/**
 * Le niveau en cours, celui dont on parle à l'utilisateur.
 *
 * Un pourcentage sur toute la collection ne dit rien à personne : « 45,5 % des
 * plages des Bouches-du-Rhône » se lit comme une corvée à moitié faite, alors
 * que la même chose dite « niveau 1 : 5 sur 8 » se lit comme trois lieux avant
 * un palier. C'est le même état, et ce n'est pas la même envie.
 */
export type Stage = {
  tier: Tier;
  visited: number;
  total: number;
  pct: number;
  remaining: number;
  /** Ce niveau-ci est terminé (donc la collection entière l'est aussi). */
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
  /** Le niveau en cours et son avancement — ce que l'écran affiche. */
  stage: Stage;
  complete: boolean;
};

function stageOf(tiers: TierProgress[]): Stage {
  const remplis = tiers.filter((tier) => tier.total > 0);
  // Le niveau en cours est le premier ouvert qu'il reste à finir. Quand il n'y
  // en a plus, on reste sur le dernier : la collection est terminée et c'est
  // ce niveau-là qu'on veut voir affiché complet.
  const courant =
    remplis.find((tier) => tier.unlocked && !tier.complete) ??
    remplis[remplis.length - 1];
  if (!courant) {
    return { tier: 1, visited: 0, total: 0, pct: 0, remaining: 0, complete: false };
  }
  return {
    tier: courant.tier,
    visited: courant.visited,
    total: courant.total,
    pct: Math.round((courant.visited / courant.total) * 1000) / 10,
    remaining: courant.total - courant.visited,
    complete: courant.complete,
  };
}

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
    stage: stageOf(tiers),
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
  const { stage } = progress;
  if (stage.total > 0 && !stage.complete) {
    return { label: `Niveau ${stage.tier}`, remaining: stage.remaining };
  }

  const threshold = BADGE_THRESHOLDS.find((value) => progress.pct < value);
  if (threshold === undefined) return null;

  const needed = Math.ceil((threshold / 100) * progress.total) - progress.visited;
  return { label: `${threshold} %`, remaining: Math.max(needed, 1) };
}


/**
 * Ce qu'une validation vient de faire bouger.
 *
 * Calculé en comparant l'avant et l'après, pour que l'écran de célébration
 * montre le mouvement plutôt qu'un état. Voir progresser une barre de 18 % à
 * 25 % vaut mieux que lire « 25 % » : c'est le mouvement qui récompense.
 */
export type CollectionAdvance = {
  collection: Collection;
  before: CollectionProgress;
  after: CollectionProgress;
  /**
   * Le niveau où le mouvement a eu lieu : celui du lieu validé.
   *
   * Pas le niveau en cours. Une validation qui TERMINE le niveau 1 le fait
   * passer au niveau 2, et une barre calée sur « le niveau en cours » repartirait
   * de zéro : le meilleur geste du jeu, affiché comme un recul.
   */
  tier: Tier;
  /** Avancement de CE niveau, avant et après. */
  fromVisited: number;
  toVisited: number;
  tierTotal: number;
};

export type CheckInReward = {
  advances: CollectionAdvance[];
  /** Badges décrochés par cette validation, et pas avant. */
  newBadges: Badge[];
  /** Niveaux terminés par cette validation. */
  tierUps: Array<{ collection: Collection; tier: Tier }>;
};

export function describeCheckIn(
  collections: Collection[],
  place: Place,
  visitsBefore: Visit[],
  visitsAfter: Visit[],
): CheckInReward {
  const advances: CollectionAdvance[] = [];
  const newBadges: Badge[] = [];
  const tierUps: Array<{ collection: Collection; tier: Tier }> = [];

  for (const collection of collections) {
    const membership = collection.places.find((member) => member.placeId === place.id);
    if (!membership) continue;

    const before = computeProgress(collection, visitsBefore);
    const after = computeProgress(collection, visitsAfter);
    if (after.visited === before.visited) continue;

    const tier = membership.tier;
    advances.push({
      collection,
      before,
      after,
      tier,
      fromVisited: before.tiers[tier - 1].visited,
      toVisited: after.tiers[tier - 1].visited,
      tierTotal: after.tiers[tier - 1].total,
    });

    const had = new Set(earnedBadges(collection, before).map((badge) => badge.id));
    for (const badge of earnedBadges(collection, after)) {
      if (!had.has(badge.id)) newBadges.push(badge);
    }

    for (const tier of after.tiers) {
      if (tier.complete && !before.tiers[tier.tier - 1].complete) {
        tierUps.push({ collection, tier: tier.tier });
      }
    }
  }

  // La collection la plus proche du but en premier : c'est celle qui parle.
  // Au niveau concerné, pas sur l'ensemble — « 7 sur 8 » passe avant « 40 sur
  // 200 », même si la seconde compte plus de lieux visités.
  advances.sort(
    (a, b) => b.toVisited / (b.tierTotal || 1) - a.toVisited / (a.tierTotal || 1),
  );
  return { advances, newBadges, tierUps };
}
