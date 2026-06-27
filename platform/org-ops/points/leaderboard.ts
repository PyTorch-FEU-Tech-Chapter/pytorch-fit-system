/**
 * Cut-throat merit leaderboard.
 *
 * This is THE competitive ranking. No equity handouts, no redistribution — raw weighted points
 * decide order. Ties are broken DETERMINISTICALLY so the ranking is stable and auditable:
 *
 *   1. higher totalPoints
 *   2. earlier firstEarnedAt  (rewarded the member who got there first)
 *   3. more recent lastActiveAt (rewarded the member still showing up)
 *   4. nickname ascending     (final deterministic fallback)
 *
 * Built on the PriorityQueue so the "heap priority queue" is the actual ranking mechanism.
 */
import { PriorityQueue } from "./heap";
import type { LeaderboardEntry, MemberStanding } from "./types";

/** true when `a` outranks `b` under the merit + tiebreaker order. */
export function outranks(a: MemberStanding, b: MemberStanding): boolean {
  if (a.totalPoints !== b.totalPoints) return a.totalPoints > b.totalPoints;

  // Earlier first-earned wins. A null (no events) is treated as "latest possible".
  const aFirst = a.firstEarnedAt ?? "￿";
  const bFirst = b.firstEarnedAt ?? "￿";
  if (aFirst !== bFirst) return aFirst < bFirst;

  // More recent activity wins. A null is treated as "earliest possible".
  const aLast = a.lastActiveAt ?? "";
  const bLast = b.lastActiveAt ?? "";
  if (aLast !== bLast) return aLast > bLast;

  return a.nickname < b.nickname;
}

/**
 * Rank standings into a leaderboard, highest first. Drains a max-heap so the ordering is exactly
 * the comparator above. `rank` is 1-based and dense (ties cannot occur — the tiebreaker is total).
 */
export function buildLeaderboard(standings: readonly MemberStanding[]): LeaderboardEntry[] {
  const queue = new PriorityQueue<MemberStanding>(outranks, standings);
  return queue.drainSorted().map((standing, i) => ({ ...standing, rank: i + 1 }));
}
