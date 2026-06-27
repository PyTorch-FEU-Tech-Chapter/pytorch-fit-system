/**
 * Point scoring — turns the append-only ledger into derived per-member standings.
 *
 * Weights encode the confirmed priority: achievements/grades/projects are the highest-priority
 * signals; referral is the lightest. Weights are the ENGINE DEFAULT; the SQL stores a `weight`
 * per row so admins can override per event. When an event carries its own weight, we trust it;
 * otherwise we apply the source default below.
 */
import type { MemberStanding, PointEvent, PointSource } from "./types";

/** Default per-source weight. Tunable; mirrors the intent in docs/POINTS-ENGINE.md. */
export const DEFAULT_SOURCE_WEIGHTS: Readonly<Record<PointSource, number>> = {
  achievement: 5,
  grade: 4,
  project: 4,
  activity: 2,
  referral: 1,
};

/** The weight to use for an event: its explicit weight if positive, else the source default. */
export function effectiveWeight(event: PointEvent): number {
  return event.weight > 0 ? event.weight : DEFAULT_SOURCE_WEIGHTS[event.source];
}

/** Weighted contribution of a single ledger row. */
export function weightedPoints(event: PointEvent): number {
  return event.points * effectiveWeight(event);
}

function minIso(a: string | null, b: string): string {
  return a === null || b < a ? b : a;
}

function maxIso(a: string | null, b: string): string {
  return a === null || b > a ? b : a;
}

/**
 * Fold the ledger into one standing per member. `nicknames` supplies the public-safe label;
 * a member with no nickname falls back to their id so the engine never invents PII.
 */
export function aggregateStandings(
  events: readonly PointEvent[],
  nicknames: ReadonlyMap<string, string>,
): MemberStanding[] {
  const byMember = new Map<string, MemberStanding>();

  for (const event of events) {
    const existing = byMember.get(event.memberId);
    const contribution = weightedPoints(event);
    if (existing) {
      byMember.set(event.memberId, {
        ...existing,
        totalPoints: existing.totalPoints + contribution,
        firstEarnedAt: minIso(existing.firstEarnedAt, event.earnedAt),
        lastActiveAt: maxIso(existing.lastActiveAt, event.earnedAt),
      });
    } else {
      byMember.set(event.memberId, {
        memberId: event.memberId,
        totalPoints: contribution,
        firstEarnedAt: event.earnedAt,
        lastActiveAt: event.earnedAt,
        nickname: nicknames.get(event.memberId) ?? event.memberId,
      });
    }
  }

  return [...byMember.values()];
}
