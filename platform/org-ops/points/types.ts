/**
 * Domain types for the Points · Leaderboard · Growth engine (org-ops layer).
 *
 * Confirmed model (docs/POINTS-ENGINE.md):
 *  - point_events is an APPEND-ONLY ledger; standings are DERIVED, never stored as truth.
 *  - The leaderboard is a CUT-THROAT MERIT ranking (no equity handouts).
 *  - The growth track is a DIAGNOSTIC engine, NOT a competing ranking.
 *
 * These mirror the SQL in supabase/migrations/0002_* and 0003_* and align with
 * platform/org-ops/types.ts naming.
 */

/** Where a point award came from. Achievements/grades/projects are the highest-priority signals. */
export type PointSource =
  | "achievement"
  | "grade"
  | "project"
  | "referral"
  | "activity";

/** One immutable row of the append-only points ledger. */
export interface PointEvent {
  id: string;
  memberId: string;
  source: PointSource;
  /** Raw points before weighting. */
  points: number;
  /** Multiplier applied per source (mirrors the SQL `weight`). */
  weight: number;
  /** ISO timestamp — passed in, never generated here (keeps the engine pure). */
  earnedAt: string;
}

/** Derived per-member totals used to build the leaderboard. */
export interface MemberStanding {
  memberId: string;
  /** Sum of points * weight across the member's ledger. */
  totalPoints: number;
  /** ISO timestamp of the member's earliest point event (tiebreaker). */
  firstEarnedAt: string | null;
  /** ISO timestamp of the member's most recent point event (tiebreaker). */
  lastActiveAt: string | null;
  /** Public-safe label only — never email/PII (SPECIFICATION §6). */
  nickname: string;
}

/** A ranked leaderboard row. Public-safe by construction. */
export interface LeaderboardEntry extends MemberStanding {
  rank: number;
}

/** A cluster groups tangible opportunities by domain (academics, tutorial, ...). */
export interface Cluster {
  id: string;
  name: string;
}

/** A concrete project/competition a member can pick from, hanging off a cluster. */
export interface ClusterItem {
  id: string;
  clusterId: string;
  title: string;
  kind: "lesson" | "event" | "hackathon" | "competition";
  /** Rough difficulty 1..5 — used by the growth engine to recommend reachable steps. */
  difficulty: number;
}

/** A pretest/posttest pair for one member on one activity. `gain = posttest - pretest`. */
export interface GrowthAssessment {
  memberId: string;
  activityId: string;
  pretest: number;
  posttest: number;
}

/** A diagnostic recommendation. Diagnostic ONLY — it never changes rank or redistributes points. */
export interface GrowthRecommendation {
  memberId: string;
  clusterItemId: string;
  reason: string;
}
