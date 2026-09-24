import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { S2Engine } from "../../../../web/static/s2-vnext/engine.js";
import { miningWork, timeForWork, earnedCores } from "../../../../web/static/s2-vnext/voyage.js";
import { replayGalaxy } from "./s2_galaxy_replay.mjs";

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

test("million-planet settlement is bounded and stops at galaxy completion with valid history and save", () => {
  const e = fixture({ resets: 20000, maxed: true });
  const started = performance.now();
  e.mineBlock(365 * 1440);
  const elapsed = performance.now() - started;
  assert.equal(e.state.completedPlanets, 1000000);
  assert.equal(e.state.resets, 999999);
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
  console.log(`million settlement: ${elapsed.toFixed(2)}ms, ${e.state.planetHistory.at(-1).minutes * 60}s/planet`);
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
  compare(a.snapshot(), b.snapshot());
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
    assert.equal(result.completedPlanets, 1000000);
    assert.ok(result.elapsedDays > 120 && result.elapsedDays < 150);
    assert.equal(result.stages.at(-1).thresholdSeconds, 1);
    assert.ok(result.stages.at(-1).seconds <= 1);
    assert.ok(result.compiled <= 80);
    assert.deepEqual(new S2Engine(data, { state: engine.snapshot() }).snapshot(), engine.snapshot());
  }
});
