/**
 * Points · Leaderboard · Growth engine — public surface.
 *
 * Pure logic only (no Supabase I/O). The persistence layer (reading the append-only point_events
 * ledger, refreshing the leaderboard matview) lives in the future Supabase data-access layer and
 * feeds these functions plain values. See platform/org-ops/points/README.md.
 */
export * from "./types";
export { PriorityQueue } from "./heap";
export {
  DEFAULT_SOURCE_WEIGHTS,
  aggregateStandings,
  effectiveWeight,
  weightedPoints,
} from "./scoring";
export { buildLeaderboard, outranks } from "./leaderboard";
export { gain, lowPointBracket, recommendGrowth } from "./growth";
export type { BracketOptions } from "./growth";
