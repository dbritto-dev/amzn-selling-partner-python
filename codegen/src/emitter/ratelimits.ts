/** Parse the "Rate (requests per second) | Burst" usage-plan tables (docs/PLAN.md §8). */

export interface RateLimit {
  rate: number;
  burst: number;
}

const TWO_COL =
  /\|\s*Rate\s*\(requests per second\)\s*\|\s*Burst\s*\|\s*\n\s*\|[\s:-]+\|[\s:-]+\|\s*\n\s*\|\s*(?<rate>[0-9]*\.?[0-9]+)\s*\|\s*(?<burst>[0-9]+)\s*\|/i;
const THREE_COL =
  /\|\s*Plan type\s*\|\s*Rate\s*\(requests per second\)\s*\|\s*Burst\s*\|\s*\n\s*\|[\s:-]+\|[\s:-]+\|[\s:-]+\|\s*\n(?:.*\n)*?\s*\|\s*Default\s*\|\s*(?<rate>[0-9]*\.?[0-9]+)\s*\|\s*(?<burst>[0-9]+)\s*\|/i;

/** The default rate limit from an operation description, or null when there is no parseable table (never guesses). */
export function parseRateLimit(description: string | undefined): RateLimit | null {
  if (!description) return null;
  const m = TWO_COL.exec(description) ?? THREE_COL.exec(description);
  if (!m || !m.groups) return null;
  const rate = Number(m.groups.rate);
  const burst = Number(m.groups.burst);
  if (!(rate > 0) || !(burst > 0)) return null;
  return { rate, burst };
}
