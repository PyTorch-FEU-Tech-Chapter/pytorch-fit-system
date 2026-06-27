/**
 * Generic binary heap (priority queue) — the "heap priority queue" the leaderboard runs on.
 *
 * Comparator returns true when `a` has HIGHER priority than `b` (should come out first).
 * A max-leaderboard passes a comparator that ranks higher points first, then applies tiebreakers.
 *
 * Pure data structure: no I/O, no clock. Mutating ops return void and operate in place on the
 * internal array; the public API never exposes that array by reference.
 */
export class PriorityQueue<T> {
  private readonly items: T[] = [];

  constructor(
    private readonly hasHigherPriority: (a: T, b: T) => boolean,
    seed: readonly T[] = [],
  ) {
    for (const item of seed) this.push(item);
  }

  get size(): number {
    return this.items.length;
  }

  isEmpty(): boolean {
    return this.items.length === 0;
  }

  peek(): T | undefined {
    return this.items[0];
  }

  push(item: T): void {
    this.items.push(item);
    this.bubbleUp(this.items.length - 1);
  }

  /** Remove and return the highest-priority item, or undefined when empty. */
  pop(): T | undefined {
    const top = this.items[0];
    const last = this.items.pop();
    if (last !== undefined && this.items.length > 0) {
      this.items[0] = last;
      this.bubbleDown(0);
    }
    return top;
  }

  /** Drain the queue into a new array, highest priority first. Leaves the queue empty. */
  drainSorted(): T[] {
    const out: T[] = [];
    let next = this.pop();
    while (next !== undefined) {
      out.push(next);
      next = this.pop();
    }
    return out;
  }

  private bubbleUp(index: number): void {
    let child = index;
    while (child > 0) {
      const parent = (child - 1) >> 1;
      if (!this.hasHigherPriority(this.items[child], this.items[parent])) break;
      this.swap(child, parent);
      child = parent;
    }
  }

  private bubbleDown(index: number): void {
    const n = this.items.length;
    let parent = index;
    for (;;) {
      const left = parent * 2 + 1;
      const right = left + 1;
      let best = parent;
      if (left < n && this.hasHigherPriority(this.items[left], this.items[best])) best = left;
      if (right < n && this.hasHigherPriority(this.items[right], this.items[best])) best = right;
      if (best === parent) break;
      this.swap(parent, best);
      parent = best;
    }
  }

  private swap(i: number, j: number): void {
    const tmp = this.items[i];
    this.items[i] = this.items[j];
    this.items[j] = tmp;
  }
}
