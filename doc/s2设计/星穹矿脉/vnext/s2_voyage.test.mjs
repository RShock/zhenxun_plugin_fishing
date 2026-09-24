import assert from "node:assert/strict";
import fs from "node:fs";
import { execFileSync } from "node:child_process";
import test from "node:test";
import { S2Engine, validateGameData } from "../../../../web/static/s2-vnext/engine.js";
import { miningWork, timeForWork, earnedCores, compileVoyage, sampleVoyage } from "../../../../web/static/s2-vnext/voyage.js";
import { replayGalaxy, calibrateGalaxyGoal } from "./s2_galaxy_replay.mjs";

const data = JSON.parse(fs.readFileSync(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url)));
function close(a, b, label = "") {
  assert.ok(Math.abs(a - b) <= 2e-7 + Math.max(Math.abs(a), Math.abs(b)) * 2e-10, `${label}: ${a} != ${b}`);
}
function compare(a, b, path = "") {
  if (typeof a === "number" && typeof b === "number") {
    const integerField = /(?:^|\.)(?:cores|resets|completedPlanets|[a-zA-Z]*[Ll]evels|totalManualCommands|autoCursor|planet|reward|day)(?:\.|$)/;
    return integerField.test(path) ? assert.equal(a, b, path) : close(a, b, path);
  }
  if (a && b && typeof a === "object" && typeof b === "object") {
    assert.deepEqual(Object.keys(a).sort(), Object.keys(b).sort(), path);
    for (const key of Object.keys(a)) compare(a[key], b[key], `${path}.${key}`);
  } else assert.deepEqual(a, b, path);
}
function fixture({ resets = 3, maxed = false, partial = false } = {}) {
  const e = new S2Engine(data); const s = e.state;
  s.resets = s.completedPlanets = resets;
  s.minute = s.planetStartedMinute = resets * 10;
  s.nextAutoMinute = (Math.floor(s.minute / 60) + 1) * 60;
  s.nextHelperMinute = (Math.floor(s.minute / 1440) + 1) * 1440;
  s.day = Math.floor(s.minute / 1440) + 1;
  s.cores = earnedCores(resets, data.prestige.rewardStep);
  s.planetHistory = Array.from({ length: Math.min(resets, 20) }, (_, i) => {
    const planet = resets - Math.min(resets, 20) + i + 1;
    return { planet, minutes: 10, completedMinute: planet * 10, reward: 1 + Math.floor((planet - 1) / 5), allMaxedMinute: null };
  });
  if (maxed) {
    for (const spec of data.prestige.upgrades) {
      const level = partial && spec.key === "galactic_drive" ? 8 : spec.maxLevel;
      for (let i = 0; i < level; i += 1) assert.equal(e.purchaseCore(spec.key).ok, true);
    }
  }
  return e;
}
function plan(e) {
  e.lastBatchSummary = { planets: 0, compiled: 0, events: 0 };
  return e.voyagePlan();
}

test("no free prestige speed; one core buys total x2 and next level costs three cores for total x3", () => {
  const e = fixture();
  assert.equal(e.prestigeSpeed(), 1);
  assert.equal(e.purchaseCore("planet_drive").ok, true);
  assert.equal(e.prestigeSpeed(), 2);
  assert.equal(e.purchaseCore("planet_drive").ok, false);
  e.state.cores += 1;
  assert.equal(e.purchaseCore("planet_drive").ok, true);
  assert.equal(e.prestigeSpeed(), 3);
  e.state.resets = 1000;
  assert.equal(e.prestigeSpeed(), 3);
});

test("factored local-age integral agrees with independent midpoint quadrature across midnight", () => {
  for (const [start, end] of [[0, 240], [239, 241], [1400, 1500], [43200, 43600], [50000, 50000.001]]) {
    const n = 100000; const dt = (end - start) / n;
    let sum = 0;
    for (let i = 0; i < n; i += 1) {
      const t = start + (i + 0.5) * dt;
      sum += (1 + 0.36 * Math.sqrt(t / 1440)) * (1 + 0.08 * Math.min(1, t % 1440 / 240)) * dt;
    }
    const exact = miningWork(start, end, 0.36, 0.08);
    assert.ok(Math.abs(exact - sum) / exact < 1e-7);
    close(timeForWork(start, exact, 0.36, 0.08), end);
  }
});

test("identical fully automated voyages retain identical durations, actual costs and a productive maxed tail", () => {
  const e = fixture(); const p = plan(e);
  assert.equal(p.events.length, 333);
  assert.ok(p.duration - p.end.allMaxedAge > 4 * 1440);
  assert.ok(p.events.every((event) => event.cost > 0));
  const expected = p.duration;
  const rng = e.rng.snapshot();
  e.mineBlock(expected * 5 + expected / 2);
  assert.equal(e.state.completedPlanets, 8);
  assert.ok(e.state.depth > 0 && e.state.depth < e.state.targetDepth);
  for (const h of e.state.planetHistory.slice(-5)) close(h.minutes, expected);
  assert.equal(e.lastBatchSummary.compiled, 0);
  assert.deepEqual(e.rng.snapshot(), rng);
  assert.deepEqual(new S2Engine(data, { state: e.snapshot() }).snapshot(), e.snapshot());
});

test("core changes invalidate the partial voyage and completed template, core balances do not", () => {
  const e = fixture({ resets: 100 });
  const a = plan(e);
  e.state.cores += 100;
  assert.equal(plan(e), a);
  e.purchaseCore("planet_drive");
  const b = plan(e);
  assert.notEqual(b, a);
  assert.ok(b.duration < a.duration);
  e.mineBlock(b.duration / 3);
  const levels = { ...e.state.levels }; const credits = e.state.credits;
  e.purchaseCore("core_refining");
  const c = plan(e);
  assert.ok(c.initialAge > 0);
  assert.deepEqual(e.state.levels, levels);
  assert.equal(e.state.credits, credits);
  assert.notEqual(c, b);
});

test("multi-million-planet settlement is bounded and stops at the configured goal with valid history and save", () => {
  const e = fixture({ resets: 500000, maxed: true });
  const started = performance.now();
  e.mineBlock(365 * 1440);
  const elapsed = performance.now() - started;
  assert.equal(e.state.completedPlanets, data.prestige.galaxyTargetPlanets);
  assert.equal(e.state.resets, data.prestige.galaxyTargetPlanets - 1);
  assert.equal(e.state.planetComplete, true);
  assert.equal(e.state.planetHistory.length, 20);
  assert.equal(e.lastBatchSummary.compiled, 1);
  assert.ok(e.lastBatchSummary.events <= 333);
  assert.ok(e.lastBlockEvents.length <= 1024);
  assert.ok(elapsed < 2000, `${elapsed}ms`);
  assert.ok(e.state.planetHistory.at(-1).minutes * 60 < 1);
  assert.deepEqual(new S2Engine(data, { state: e.snapshot() }).snapshot(), e.snapshot());
  const cores = e.state.cores; const levels = e.state.totalAutoLevels;
  assert.equal(e.departPlanet().reason, "galaxy");
  e.mineBlock(1440);
  assert.equal(e.state.cores, cores); assert.equal(e.state.totalAutoLevels, levels);
  console.log(`galaxy settlement: ${elapsed.toFixed(2)}ms, ${e.state.planetHistory.at(-1).minutes * 60}s/planet`);
});

test("batched settlement matches an independent per-planet reward/reset loop", () => {
  const fast = fixture({ resets: 20000, maxed: true, partial: true });
  const slow = new S2Engine(data, { state: fast.snapshot() });
  const p = plan(fast);
  const start = slow.state.minute;
  fast.mineBlock(p.duration * 151.25);
  // This reference never uses the batch reducer or core prefix-sum to award.
  for (let i = 0; i < 151; i += 1) {
    const s = slow.state;
    s.minute = start + p.duration * (i + 1);
    s.depth = s.targetDepth;
    s.totalAutoLevels += p.end.built;
    s.allMaxedMinute = p.end.allMaxedAge === null ? null : start + p.duration * i + p.end.allMaxedAge;
    slow.finishPlanet();
    slow.departPlanet();
  }
  slow.syncVoyageClock(start + p.duration * 151);
  slow.mineBlock(start + p.duration * 151.25 - slow.state.minute);
  compare(fast.snapshot(), slow.snapshot());
});

test("continuous partitioning and save/reload preserve partial progress without changing RNG", () => {
  const seed = fixture({ resets: 100, maxed: false });
  seed.purchaseCore("planet_drive");
  const a = new S2Engine(data, { state: seed.snapshot() });
  let b = new S2Engine(data, { state: seed.snapshot() });
  a.mineBlock(100000);
  for (let i = 0; i < 100; i += 1) {
    b.mineBlock(1000);
    if (i % 7 === 0) b = new S2Engine(data, { state: JSON.parse(JSON.stringify(b.snapshot())) });
  }
  compare(a.snapshot(), b.snapshot());
});

test("core auto-purchase boundaries match small advances, including unlocks and saved partial cycles", () => {
  const initial = fixture({ resets: 100 });
  const a = new S2Engine(data, { state: initial.snapshot() });
  let b = new S2Engine(data, { state: initial.snapshot() });
  a.setCoreAutoRoute("balanced"); b.setCoreAutoRoute("balanced");
  a.mineBlock(14400);
  for (let i = 0; i < 1440; i += 1) {
    b.mineBlock(10);
    if (i === 37) b = new S2Engine(data, { state: b.snapshot() });
  }
  const left = a.snapshot(); const right = b.snapshot();
  // Repeated global-clock additions may drift by nanoseconds. Propagate that
  // measured drift through production; core balances and levels remain exact.
  const clockDrift = Math.abs(a.state.planetStartedMinute - b.state.planetStartedMinute);
  assert.ok(clockDrift < 1e-8, `clock drift: ${clockDrift} minutes`);
  for (const [key, rate] of [
    ["credits", data.rules.baseCreditsPerMinute * Math.max(a.incomeMultiplier(), b.incomeMultiplier())],
    ["depth", data.rules.baseDepthPerMinute * Math.max(a.depthMultiplier(), b.depthMultiplier())],
  ]) {
    assert.ok(Math.abs(left.state[key] - right.state[key]) <= 2e-7 + 2 * clockDrift * rate, key);
    right.state[key] = left.state[key];
  }
  compare(left, right);
  assert.ok(a.state.completedPlanets > 100);
  assert.ok(a.lastBatchSummary.compiled <= 80);
});

test("disabled auto departure completes exactly one planet and never spends cores while disabled", () => {
  const e = fixture({ resets: 20000, maxed: true, partial: true });
  e.setAutoDepart(false);
  const before = e.state.cores;
  const p = plan(e);
  e.mineBlock(60);
  assert.equal(e.state.completedPlanets, 20001);
  assert.equal(e.state.resets, 20000);
  close(e.state.planetHistory.at(-1).minutes, p.duration);
  assert.equal(e.state.cores, before + 4001);
  assert.deepEqual(new S2Engine(data, { state: e.snapshot() }).snapshot(), e.snapshot());
  e.mineBlock(60); assert.equal(e.state.completedPlanets, 20001);
});

test("prestige-1 migration adds no gifted speed or spending and retains existing permanent research", () => {
  const e = fixture({ resets: 100 });
  e.purchaseCore("core_drill");
  const old = e.snapshot(); old.state.contentVersion = "prestige-1";
  delete old.state.coreLevels.planet_drive;
  delete old.state.coreAutoRoute;
  const untouched = structuredClone(old);
  const restored = new S2Engine(data, { state: old });
  assert.equal(restored.state.coreLevels.planet_drive, 0);
  assert.equal(restored.prestigeSpeed(), 1);
  assert.equal(restored.state.coreAutoRoute, "off");
  assert.equal(restored.state.coreLevels.core_drill, 1);
  assert.equal(restored.state.cores, e.state.cores);
  assert.deepEqual(old, untouched);
});

test("current saves reject missing permanent levels, invalid routes and duplicate reward history", () => {
  const original = fixture({ resets: 100 });
  for (const corrupt of [
    (s) => { delete s.coreLevels.planet_drive; },
    (s) => { delete s.coreAutoRoute; },
    (s) => { s.coreAutoRoute = "unknown"; },
    (s) => { s.cores += 1; },
    (s) => { s.planetHistory.at(-1).planet -= 1; },
  ]) {
    const saved = original.snapshot();
    corrupt(saved.state);
    const before = original.snapshot();
    assert.throws(() => original.restore(saved));
    assert.deepEqual(original.snapshot(), before);
  }
});

test("partial voyage research and repeated reloads match uninterrupted settlement", () => {
  const initial = fixture({ resets: 100 });
  initial.mineBlock(20000);
  const a = new S2Engine(data, { state: initial.snapshot() });
  let b = new S2Engine(data, { state: initial.snapshot() });
  for (const key of ["planet_drive", "core_depth", "core_refining", "stellar_relay"]) {
    assert.equal(a.purchaseCore(key).ok, true);
    assert.equal(b.purchaseCore(key).ok, true);
    a.mineBlock(6000);
    for (let i = 0; i < 12; i += 1) {
      b.mineBlock(500);
      b = new S2Engine(data, { state: JSON.parse(JSON.stringify(b.snapshot())) });
    }
    compare(a.snapshot(), b.snapshot());
  }
});

test("each compiled purchase is paid, meets depth and prerequisites, and has the correct price", () => {
  const e = fixture();
  const p = e.voyagePlan();
  const verifier = fixture();
  let earned = 0; let spent = 0; let depth = 0;
  for (const segment of p.segments) {
    const previous = verifier.state;
    const events = p.events.filter((event) => event.age === segment.age);
    close(segment.depth, depth, "depth carried from prior mining");
    spent += events.reduce((sum, event) => sum + event.cost, 0);
    close(segment.credits + spent, earned, "purchases funded by prior mining");
    assert.ok(segment.credits >= 0);
    for (const event of events) {
      // Use the compiled balances only to reconstruct this boundary, then let
      // the independent purchase API enforce actual prices and prerequisites.
      const rest = events.filter((item) => item !== event && item.level > verifier.level(item.key));
      verifier.state.depth = segment.depth;
      verifier.state.credits = segment.credits + event.cost + rest.reduce((n, item) => n + item.cost, 0);
      assert.equal(event.level, verifier.level(event.key) + 1);
      assert.equal(event.cost, verifier.costFor(event.key));
      assert.equal(verifier.available(event.key, true), true);
      assert.equal(verifier.purchase(event.key, true).ok, true);
    }
    assert.deepEqual(previous.levels, segment.levels);
    const work = miningWork(segment.age, segment.endAge, segment.teamwork, segment.momentum);
    earned += work * segment.income;
    depth += work * segment.depthRate;
  }
  close(p.end.credits + spent, earned, "final income conservation");
  close(p.end.depth, depth, "final depth conservation");
  assert.deepEqual(verifier.state.levels, p.end.levels);
});

test("natural daily and absent starts reach second-level voyages and the galaxy without gifted research", () => {
  for (const profile of ["daily", "absent"]) {
    const { engine, result } = replayGalaxy(data, { profile, route: "balanced", days: 180 });
    assert.equal(result.completedPlanets, data.prestige.galaxyTargetPlanets);
    assert.ok(result.elapsedDays > 120 && result.elapsedDays < 180);
    assert.equal(result.stages.at(-1).thresholdSeconds, 1);
    assert.ok(result.stages.at(-1).seconds <= 1);
    assert.ok(result.compiled <= 100);
    assert.equal(result.research.length, data.prestige.upgrades.reduce((n, spec) => n + spec.maxLevel, 0));
    assert.ok(result.productiveTailDays >= 5 && result.productiveTailDays < 5.02);
    assert.ok(result.researchComplete.planets < result.completedPlanets);
    assert.deepEqual(new S2Engine(data, { state: engine.snapshot() }).snapshot(), engine.snapshot());
  }
});

test("burst is integrated only during the first second, including a purchase inside that second", () => {
  const e = fixture({ resets: 1200 });
  // This tiny controlled planet finishes before any local technology is affordable.
  e.state.minute = 0; e.state.planetStartedMinute = 0; e.state.targetDepth = 20;
  e.purchaseCore("big_bang");
  const p = compileVoyage(e);
  const boundary = 1 / 60;
  assert.equal(p.segments[0].endAge, boundary);
  close(p.segments[0].depthRate, 25 * 34);
  close(p.segments[1].depthRate, 25);
  close(sampleVoyage(p, boundary).depth, 25 * 34 / 60);
  close(p.duration, boundary + (20 - 25 * 34 / 60) / 25);
  close(p.end.credits, 20 * 8 / 25);

  const late = fixture({ resets: 1200 });
  late.mineBlock(0.5 / 60);
  const prior = late.state.depth;
  late.purchaseCore("big_bang");
  late.mineBlock(1 / 60);
  close(late.state.depth - prior, 25 * (34 * 0.5 + 0.5) / 60);
  assert.equal(late.multiplierBreakdown().opening_burst, 1);
  const levelBefore = late.state.coreLevels.big_bang;
  late.state.cores += 1e6;
  late.purchaseCore("big_bang");
  assert.equal(late.state.coreLevels.big_bang, levelBefore + 1);
  assert.equal(late.multiplierBreakdown().opening_burst, 1);
});

test("burst partial save, reload and one large step agree across the expiry boundary", () => {
  const e = fixture({ resets: 1200 });
  e.purchaseCore("big_bang");
  e.mineBlock(0.4 / 60);
  const a = new S2Engine(data, { state: e.snapshot() });
  let b = new S2Engine(data, { state: e.snapshot() });
  a.mineBlock(3 / 60);
  for (let i = 0; i < 6; i += 1) {
    b.mineBlock(0.5 / 60);
    b = new S2Engine(data, { state: b.snapshot() });
  }
  compare(a.snapshot(), b.snapshot());
});

test("discount changes only local prices and full-build depth activates only after rebuilding every technology", () => {
  const e = fixture({ resets: 100 });
  const price = e.costFor("rotary_pick");
  const corePrice = e.coreCost("core_drill");
  const income = e.incomeMultiplier(); const depth = e.depthMultiplier();
  e.purchaseCore("stellar_procurement");
  assert.equal(e.costFor("rotary_pick"), price / 1.25);
  assert.equal(e.coreCost("core_drill"), corePrice);
  assert.equal(e.incomeMultiplier(), income); assert.equal(e.depthMultiplier(), depth);
  e.purchaseCore("planetary_exhaustion");
  assert.equal(e.multiplierBreakdown().completion_depth, 1);
  for (const key of e.localKeys) e.state.levels[key] = e.specs[key].maxLevel;
  assert.equal(e.multiplierBreakdown().completion_depth, 2);
  const fullIncome = e.incomeMultiplier(); const fullDepth = e.depthMultiplier();
  e.state.coreLevels.planetary_exhaustion = 0;
  close(e.incomeMultiplier(), fullIncome); close(e.depthMultiplier(), fullDepth / 2);
  e.state.coreLevels.planetary_exhaustion = 1;
  e.clearLocalPlanet();
  assert.equal(e.multiplierBreakdown().completion_depth, 1);
});

test("routes bootstrap cheaply, then save for their selected preference without crossing unlock boundaries", () => {
  for (const route of ["balanced", "speed", "rebuild", "burst"]) {
    const e = fixture({ resets: 1 });
    e.setCoreAutoRoute(route);
    assert.equal(e.state.coreLevels.planet_drive, 1);
    assert.equal(e.state.cores, 0);
  }
  const e = fixture({ resets: 999 });
  e.state.coreAutoRoute = "burst";
  // The next planet unlocks Big Bang and may change the selected savings target.
  assert.equal(e.planetsUntilCorePurchase(1000), 1);
  const f = fixture({ resets: 10 });
  f.state.cores = 2;
  f.state.coreLevels.planet_drive = 1;
  f.state.coreLevels.core_drill = 1;
  f.setCoreAutoRoute("speed");
  assert.equal(f.state.cores, 2, "wait for preferred 3-core engine instead of spending on 2-core refining");
});

test("research has value in its intended phase and burst changes from marginal to dominant", () => {
  const full = fixture({ resets: 500000, maxed: true });
  const duration = plan(full).duration;
  for (const spec of data.prestige.upgrades) {
    if (spec.effectKind === "completion_depth") continue;
    const reduced = new S2Engine(data, { state: full.snapshot() });
    reduced.state.coreLevels[spec.key] -= 1;
    assert.ok(plan(reduced).duration > duration * 1.00001, spec.key);
  }
  const finisher = fixture({ resets: 100 });
  const unfinishedDuration = plan(finisher).duration;
  finisher.purchaseCore("planetary_exhaustion");
  assert.ok(unfinishedDuration / plan(finisher).duration > 1.05);
  assert.equal(finisher.coreSpecs.planetary_exhaustion.maxLevel, 3, "early specialist ends cheaply rather than pretending to scale late");
  const early = fixture({ resets: 1200 });
  const baseline = plan(early).duration;
  early.purchaseCore("big_bang");
  const earlyGain = baseline / plan(early).duration;
  assert.ok(earlyGain > 1 && earlyGain < 1.001, String(earlyGain));
  const without = new S2Engine(data, { state: full.snapshot() });
  without.state.coreLevels.big_bang = 0;
  assert.ok(plan(without).duration / duration > 90);
});

test("prestige-2 real historical save migrates spending at old prices, then new purchases use current prices", () => {
  const oldData = JSON.parse(execFileSync("git", ["show", "1883bef:web/static/s2-vnext/game_data.json"],
    { cwd: new URL("../../../../", import.meta.url), encoding: "utf8" }));
  const old = fixture({ resets: 1000 }).snapshot();
  old.state.contentVersion = "prestige-2";
  delete old.state.legacyCoreLevels;
  old.state.coreLevels = Object.fromEntries(oldData.prestige.upgrades.map((spec) => [spec.key, 2]));
  old.state.cores = earnedCores(1000, data.prestige.rewardStep)
    - oldData.prestige.upgrades.reduce((n, spec) => n + spec.baseCost * (1 + spec.costGrowth), 0);
  const untouched = structuredClone(old);
  const e = new S2Engine(data, { state: old });
  assert.deepEqual(old, untouched);
  assert.equal(e.state.coreAutoRoute, "off");
  assert.equal(e.state.coreLevels.big_bang, 0);
  assert.equal(e.state.legacyCoreLevels.core_drill, 2);
  const before = e.state.cores;
  assert.equal(e.purchaseCore("core_drill").ok, true);
  assert.equal(e.state.cores, before - e.coreSpecs.core_drill.baseCost * e.coreSpecs.core_drill.costGrowth ** 2);
  assert.deepEqual(new S2Engine(data, { state: e.snapshot() }).snapshot(), e.snapshot());
  for (const damage of [
    (s) => { delete s.legacyCoreLevels; },
    (s) => { s.legacyCoreLevels.core_drill = 9; },
    (s) => { s.legacyCoreLevels.big_bang = 1; },
    (s) => { s.cores += 1; },
  ]) {
    const broken = e.snapshot(); damage(broken.state);
    assert.throws(() => new S2Engine(data, { state: broken }));
  }
});

test("all preset routes finish research before the configured productive tail", () => {
  for (const route of ["speed", "rebuild", "burst"]) {
    const { result, engine } = replayGalaxy(data, { route, days: 220 });
    assert.equal(result.completedPlanets, data.prestige.galaxyTargetPlanets, route);
    assert.ok(result.productiveTailDays >= 5 && result.productiveTailDays < 5.02, route);
    assert.deepEqual(new S2Engine(data, { state: engine.snapshot() }).snapshot(), engine.snapshot());
  }
});

test("galaxy target is derived from completed research plus five productive days", () => {
  const original = structuredClone(data);
  const result = calibrateGalaxyGoal(data, { days: 180 });
  assert.equal(result.recommendedTarget, data.prestige.galaxyTargetPlanets);
  assert.ok(result.actualTailDays >= 5 && result.actualTailDays < 5.02);
  assert.ok(result.researchComplete.planets < result.recommendedTarget);
  assert.ok(result.finalSeconds > 0 && result.finalSeconds < 1);
  assert.deepEqual(data, original);
  assert.throws(() => calibrateGalaxyGoal(data, { tailDays: 0 }));
  assert.throws(() => calibrateGalaxyGoal(data, { roundTo: 0 }));
  const unsafe = structuredClone(data);
  unsafe.prestige.galaxyTargetPlanets = 1e9;
  assert.throws(() => validateGameData(unsafe), /prestige/);
});
