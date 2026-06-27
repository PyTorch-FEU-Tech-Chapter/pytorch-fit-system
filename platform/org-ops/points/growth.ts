/**
 * Growth track — a DIAGNOSTIC / RECOMMENDATION engine. NOT a competing leaderboard.
 *
 * It never changes anyone's rank and never redistributes points. Its only job: look at the
 * LOW-POINT bracket and their pretest/posttest GAIN, then surface which reachable lessons/events/
 * hackathons would help them climb toward the high-point level. The merit competition stays
 * cut-throat; this is the chance-to-grow pathway the org provides on the side.
 */
import type {
  Cluster,
  ClusterItem,
  GrowthAssessment,
  GrowthRecommendation,
  LeaderboardEntry,
} from "./types";

/** gain = posttest - pretest. Negative gain is valid (the member regressed). */
export function gain(assessment: GrowthAssessment): number {
  return assessment.posttest - assessment.pretest;
}

export interface BracketOptions {
  /** Members in the bottom `lowFraction` of the ranking are the low-point bracket. 0..1. */
  lowFraction: number;
}

const DEFAULT_BRACKET: BracketOptions = { lowFraction: 0.5 };

/** Member ids in the bottom fraction of the leaderboard (the ones the growth track serves). */
export function lowPointBracket(
  leaderboard: readonly LeaderboardEntry[],
  options: BracketOptions = DEFAULT_BRACKET,
): Set<string> {
  const total = leaderboard.length;
  if (total === 0) return new Set();
  const cutoff = Math.ceil(total * (1 - clamp01(options.lowFraction)));
  return new Set(leaderboard.filter((e) => e.rank > cutoff).map((e) => e.memberId));
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/**
 * Recommend reachable next steps for low-bracket members.
 *
 * Heuristic (deterministic, explainable — no AI required):
 *  - Only low-bracket members get recommendations.
 *  - A member's "reach level" is derived from their best recent gain: more gain → can handle a
 *    harder item. We map gain to a difficulty ceiling and recommend items at or below it,
 *    preferring the hardest reachable item per cluster so they actually move up.
 *
 * `assessmentsByMember` holds each member's assessments; we use their max gain as the signal.
 */
export function recommendGrowth(
  leaderboard: readonly LeaderboardEntry[],
  assessmentsByMember: ReadonlyMap<string, readonly GrowthAssessment[]>,
  clusters: readonly Cluster[],
  items: readonly ClusterItem[],
  options: BracketOptions = DEFAULT_BRACKET,
): GrowthRecommendation[] {
  const bracket = lowPointBracket(leaderboard, options);
  const itemsByCluster = groupByCluster(items);
  const clusterName = new Map(clusters.map((c) => [c.id, c.name]));
  const out: GrowthRecommendation[] = [];

  for (const memberId of bracket) {
    const ceiling = difficultyCeiling(assessmentsByMember.get(memberId) ?? []);
    for (const [clusterId, clusterItems] of itemsByCluster) {
      const reachable = clusterItems
        .filter((it) => it.difficulty <= ceiling)
        .sort((a, b) => b.difficulty - a.difficulty);
      const pick = reachable[0];
      if (!pick) continue;
      out.push({
        memberId,
        clusterItemId: pick.id,
        reason: `Reachable ${pick.kind} in ${clusterName.get(clusterId) ?? clusterId} ` +
          `(difficulty ${pick.difficulty} ≤ your reach ${ceiling}) to climb toward the top bracket.`,
      });
    }
  }
  return out;
}

/** Map a member's best gain to the hardest difficulty (1..5) they should attempt next. */
function difficultyCeiling(assessments: readonly GrowthAssessment[]): number {
  if (assessments.length === 0) return 1; // no signal yet — start gentle
  const bestGain = Math.max(...assessments.map(gain));
  // 0 or negative gain → stay at 1; each +5 gain unlocks one difficulty step, capped at 5.
  return Math.min(5, Math.max(1, 1 + Math.floor(Math.max(0, bestGain) / 5)));
}

function groupByCluster(items: readonly ClusterItem[]): Map<string, ClusterItem[]> {
  const map = new Map<string, ClusterItem[]>();
  for (const item of items) {
    const list = map.get(item.clusterId);
    if (list) list.push(item);
    else map.set(item.clusterId, [item]);
  }
  return map;
}
