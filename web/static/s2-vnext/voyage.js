// Integrate the existing local-age effects between actual purchase/unlock events.
// Factored root differences avoid cancellation when a late voyage lasts seconds.
export function miningWork(start, end, teamwork, momentum) {
  if (end <= start) return 0;
  let t = start; let total = 0; let pieces = 0;
  const a = teamwork / Math.sqrt(1440);
  while (t < end) {
    if (++pieces > 8192) throw new Error("Voyage age integration exceeded its bounded horizon");
    const day = Math.floor(t / 1440) * 1440;
    const ramp = t - day < 240;
    const stop = Math.min(end, day + (ramp ? 240 : 1440));
    const h = stop - t;
    const root = Math.sqrt(t);
    const delta = h / (Math.sqrt(stop) + root);
    const rootIntegral = 2 * root * root * delta + 2 * root * delta ** 2 + 2 / 3 * delta ** 3;
    const base = h + a * rootIntegral;
    if (ramp) {
      const weightedRoot = 2 * root ** 3 * delta ** 2 + 10 / 3 * root ** 2 * delta ** 3
        + 2 * root * delta ** 4 + 2 / 5 * delta ** 5;
      total += (1 + momentum * (t - day) / 240) * base
        + momentum / 240 * (h * h / 2 + a * weightedRoot);
    } else total += (1 + momentum) * base;
    t = stop;
  }
  return total;
}

export function timeForWork(start, work, teamwork, momentum) {
  if (!(work > 0) || !Number.isFinite(work)) throw new Error("Invalid voyage event distance");
  if (!teamwork && !momentum) return start + work;
  let lo = start;
  let hi = start + work / (1 + teamwork * Math.sqrt(start / 1440));
  if (!(hi > start)) throw new Error("Voyage event below clock precision");
  for (let i = 0; i < 52; i += 1) {
    const mid = lo + (hi - lo) / 2;
    if (miningWork(start, mid, teamwork, momentum) < work) lo = mid;
    else hi = mid;
  }
  return hi;
}

export function earnedCores(planets, step) {
  const q = Math.floor(planets / step); const r = planets % step;
  return planets + step * q * (q - 1) / 2 + q * r;
}

function localSnapshot(engine, eraAges) {
  const s = engine.state;
  return {
    age: s.minute, depth: s.depth, credits: s.credits,
    levels: { ...s.levels }, manualLevels: { ...s.manualLevels },
    autoUnlocked: [...s.autoUnlocked], everKeys: [...s.everKeys],
    eraAges: { ...eraAges }, allMaxedAge: s.allMaxedMinute,
    built: Object.values(s.levels).reduce((sum, level) => sum + level, 0),
  };
}

// The scratch engine has no global clock or core purchases. The caller splits at
// permanent-research boundaries and settles global history/rewards separately.
export function compileVoyage(engine) {
  const s = engine.state;
  const initialAge = s.minute;
  const eraAges = {};
  const segments = [];
  const events = [];
  const maxEvents = engine.localKeys.reduce((n, key) => n + engine.specs[key].maxLevel * 2, 0)
    + engine.localKeys.length + 10;
  for (let i = 0; i < maxEvents; i += 1) {
    if (s.depth >= s.targetDepth) {
      return { initialAge, segments, events, end: localSnapshot(engine, eraAges), duration: s.minute };
    }
    const previousEras = new Set(Object.keys(s.eraFirstDays));
    const purchases = engine.autoPurchase();
    for (const era of Object.keys(s.eraFirstDays)) {
      if (!previousEras.has(era)) eraAges[era] = s.minute;
    }
    for (const item of purchases) events.push({ ...item, age: s.minute });
    const f = engine.multiplierBreakdown();
    const e = engine.effectLevels();
    const income = engine.rules.baseCreditsPerMinute * engine.incomeMultiplier() / f.teamwork / f.momentum;
    const depth = engine.rules.baseDepthPerMinute * engine.depthMultiplier() / f.teamwork / f.momentum;
    const teamwork = e.teamwork || 0; const momentum = e.momentum || 0;
    let work = (s.targetDepth - s.depth) / depth;
    let boundary = { kind: "depth", value: s.targetDepth };
    for (const key of engine.localKeys) {
      const spec = engine.specs[key];
      if (spec.status !== "active" || engine.level(key) >= spec.maxLevel
        || !spec.prerequisites.every((required) => engine.level(required) >= 1)) continue;
      const era = engine.eraByKey[spec.era];
      const previous = engine.eraSequence[engine.eraSequence.indexOf(spec.era) - 1];
      if (previous && engine.eraAutomationCount(previous) < era.previousEraAutomations) continue;
      const neededDepth = Math.max(spec.unlockDepth, era.unlockDepth);
      const isDepth = s.depth < neededDepth;
      const value = isDepth ? neededDepth : engine.costFor(key);
      const distance = isDepth ? (value - s.depth) / depth : (value - s.credits) / income;
      if (distance > 0 && distance < work) {
        work = distance; boundary = { kind: isDepth ? "depth" : "credits", value };
      }
    }
    const nextAge = timeForWork(s.minute, work, teamwork, momentum);
    if (!Number.isFinite(nextAge) || nextAge <= s.minute) throw new Error("Non-progressing voyage event");
    segments.push({ ...localSnapshot(engine, eraAges), endAge: nextAge, income, depthRate: depth, teamwork, momentum });
    s.credits += income * work;
    s.depth = Math.min(s.targetDepth, s.depth + depth * work);
    s[boundary.kind] = Math.max(s[boundary.kind], boundary.value);
    s.minute = nextAge;
    s.day = Math.floor(s.minute / 1440) + 1;
  }
  throw new Error("Voyage exceeded the finite local upgrade event budget");
}

export function sampleVoyage(plan, age) {
  if (age >= plan.duration) return plan.end;
  let lo = 0; let hi = plan.segments.length;
  while (lo + 1 < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (plan.segments[mid].age <= age) lo = mid; else hi = mid;
  }
  const segment = plan.segments[lo];
  const work = miningWork(segment.age, age, segment.teamwork, segment.momentum);
  return { ...segment, age, credits: segment.credits + segment.income * work,
    depth: segment.depth + segment.depthRate * work };
}
