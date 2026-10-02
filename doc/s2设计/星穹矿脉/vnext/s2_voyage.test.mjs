import assert from "node:assert/strict";
import fs from "node:fs";
import { execFileSync } from "node:child_process";
import test from "node:test";
import { S2Engine, validateGameData } from "../../../../web/static/s2-vnext/engine.js";
import { miningWork, timeForWork, earnedCores, compileVoyage, sampleVoyage } from "../../../../web/static/s2-vnext/voyage.js";
import { replayGalaxy, calibrateGalaxyGoal } from "./s2_galaxy_replay.mjs";

const data = JSON.parse(fs.readFileSync(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url)));
function close(a, b, label = "", scale = 1) {
  assert.ok(Math.abs(a - b) <= scale * (2e-7 + Math.max(Math.abs(a), Math.abs(b)) * 2e-10), `${label}: ${a} != ${b}`);
}
// scale：参考实现逐颗累加浮点数时会比批量结算多攒一点舍入误差，允许按倍数放宽容差
function compare(a, b, path = "", scale = 1) {
  if (typeof a === "number" && typeof b === "number") {
    const integerField = /(?:^|\.)(?:cores|resets|completedPlanets|[a-zA-Z]*[Ll]evels|totalManualCommands|autoCursor|planet|reward|day)(?:\.|$)/;
    return integerField.test(path) ? assert.equal(a, b, path) : close(a, b, path, scale);
  }
  if (a && b && typeof a === "object" && typeof b === "object") {
    assert.deepEqual(Object.keys(a).sort(), Object.keys(b).sort(), path);
    for (const key of Object.keys(a)) compare(a[key], b[key], `${path}.${key}`, scale);
  } else assert.deepEqual(a, b, path);
}
// 这些夹具合成的是「教学期之后」的存档：前 5 次启程必须亲手点（rules.manualDepartures）
// 是面向新玩家的引导，与航程数学无关，故在夹具里置零；该规则本身由文件末尾的专门用例覆盖。
const voyageData = { ...data, rules: { ...data.rules, manualDepartures: 0 } };
function fixture({ resets = 3, maxed = false, partial = false } = {}) {
  const e = new S2Engine(voyageData); const s = e.state;
  // 永久科技的夜班助手会自己花核心，会盖住本文件要测的航程数学；这里关掉，由夹具自己摆科技等级。
  e.setCoreHelperEnabled(false);
  s.resets = s.completedPlanets = resets;
  // 刚刚启程到达的新星球：本地矿币清零（开局 300 矿币只在第一颗星球发放一次）。
  s.credits = 0;
  s.minute = s.planetStartedMinute = resets * 10;
  s.nextAutoMinute = (Math.floor(s.minute / 60) + 1) * 60;
  s.nextHelperMinute = (Math.floor(s.minute / 1440) + 1) * 1440;
  s.day = Math.floor(s.minute / 1440) + 1;
  // 规则变更（2026-10-02）：跨越星区会额外发放奖励核心，存档对账把它算进「理论产出」
  s.cores = earnedCores(resets, data.prestige.rewardStep) + e.sectorBonusCores(resets);
  s.planetHistory = Array.from({ length: Math.min(resets, 20) }, (_, i) => {
    const planet = resets - Math.min(resets, 20) + i + 1;
    return { planet, minutes: 10, completedMinute: planet * 10, reward: 1 + Math.floor((planet - 1) / 5), allMaxedMinute: null };
  });
  if (maxed) {
    // 只买本阶段已解锁的科技：二阶段科技的解锁门槛现在一路铺到 3,600 万颗，
    // 在 resets=3 的夹具里绝大多数还没开放。
    for (const spec of data.prestige.upgrades) {
      if (spec.unlockResets > s.completedPlanets) continue;
      const level = partial && spec.key === "galactic_drive" ? 8 : spec.maxLevel;
      // 核心不够就停在买得起的层级（二阶段科技的满级造价已超过此时的理论总产出）；
      // 其它失败原因仍然视为引擎缺陷。
      // grant 通道：夹具直接把等级摆上去，不受"亲手 3 级才转自动"的渠道限制
      for (let i = 0; i < level; i += 1) {
        const bought = e.purchaseCore(spec.key, { grant: true });
        if (!bought.ok) { assert.equal(bought.reason, "cores"); break; }
      }
    }
  }
  return e;
}
// 「开局爆发」已被重排到二阶段（解锁门槛随版本调整），用例跟着数据走，不再写死 1200 颗。
const burstResets = Number(data.prestige.upgrades.find((item) => item.key === "big_bang").unlockResets);
// 从当前等级反推"这些永久科技一共花了多少核心"，用于核对"核心只来自产出"
function coreSpent(e) {
  return Object.values(e.coreSpecs).reduce((sum, spec) => {
    let total = 0;
    for (let i = 0; i < e.state.coreLevels[spec.key]; i += 1) total += spec.baseCost * spec.costGrowth ** i;
    return sum + total;
  }, 0);
}
function plan(e) {
  e.lastBatchSummary = { planets: 0, compiled: 0, events: 0 };
  return e.voyagePlan();
}

test("no free prestige speed; one core buys total x2 and next level costs three cores for total x3", () => {
  const e = fixture();
  const spec = data.prestige.upgrades.find((item) => item.key === "planet_drive");
  const eff = Number(spec.effectPerLevel);
  assert.equal(e.prestigeSpeed(), 1);
  assert.equal(e.purchaseCore("planet_drive").ok, true);
  assert.equal(e.prestigeSpeed(), 1 + eff);
  assert.equal(e.purchaseCore("planet_drive").ok, false);
  e.state.cores += 1;
  assert.equal(e.purchaseCore("planet_drive").ok, true);
  assert.equal(e.prestigeSpeed(), 1 + eff * 2);
  e.state.resets = 1000;
  assert.equal(e.prestigeSpeed(), 1 + eff * 2);
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
  assert.equal(p.events.length, 340);
  assert.ok(p.duration - p.end.allMaxedAge > 2 * 1440);
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
  // 每买一级永久科技就要重编一次航程；关键是它与"星球颗数"无关，而不是恒等于 1
  assert.ok(e.lastBatchSummary.compiled <= 5, String(e.lastBatchSummary.compiled));
  // 事件条数只跟"科技一共有多少级"挂钩（每级购买会播报），与 2728 万颗星球的颗数无关
  assert.ok(e.lastBatchSummary.events <= data.prestige.upgrades.reduce((n, spec) => n + spec.maxLevel, 0) * 3,
    String(e.lastBatchSummary.events));
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
  const start = slow.state.minute;
  let elapsed = 0; let last = 0;
  // This reference never uses the batch reducer or core prefix-sum to award.
  // 自动线每买一级永久科技都会改变航程长度，所以这里逐颗重算，不能复用同一份 plan。
  for (let i = 0; i < 151; i += 1) {
    const p = plan(slow);
    const s = slow.state;
    const from = start + elapsed;
    elapsed += p.duration; last = p.duration;
    s.minute = from + p.duration;
    s.depth = s.targetDepth;
    s.totalAutoLevels += p.end.built;
    s.allMaxedMinute = p.end.allMaxedAge === null ? null : from + p.end.allMaxedAge;
    slow.finishPlanet();
    slow.autoPurchaseCore();
    slow.departPlanet();
  }
  fast.mineBlock(elapsed + last * 0.25);
  slow.syncVoyageClock(start + elapsed);
  slow.mineBlock(start + elapsed + last * 0.25 - slow.state.minute);
  compare(fast.snapshot(), slow.snapshot(), "", 20);
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
  a.setCoreHelperEnabled(true); b.setCoreHelperEnabled(true);
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
  // 重编次数跟"买了多少级永久科技"走，而不是跟几千颗星球走
  assert.ok(a.lastBatchSummary.compiled <= data.prestige.upgrades.reduce((n, spec) => n + spec.maxLevel, 0),
    String(a.lastBatchSummary.compiled));
});

test("disabled auto departure completes exactly one planet and never spends cores while disabled", () => {
  const e = fixture({ resets: 20000, maxed: true, partial: true });
  e.setAutoDepart(false);
  const before = e.state.cores; const spentBefore = coreSpent(e);
  const p = plan(e);
  e.mineBlock(60);
  assert.equal(e.state.completedPlanets, 20001);
  assert.equal(e.state.resets, 20000);
  close(e.state.planetHistory.at(-1).minutes, p.duration);
  // 已转自动的科技会继续自己买，所以核对的是"净产出"：这一颗星球只发了 4001 枚核心
  assert.equal(e.state.cores + coreSpent(e) - spentBefore, before + 4001);
  assert.deepEqual(new S2Engine(data, { state: e.snapshot() }).snapshot(), e.snapshot());
  e.mineBlock(60); assert.equal(e.state.completedPlanets, 20001);
});

test("current saves reject missing permanent levels, broken commissioning and duplicate reward history", () => {
  const original = fixture({ resets: 100 });
  original.purchaseCore("planet_drive");
  for (const corrupt of [
    (s) => { delete s.coreLevels.planet_drive; },
    (s) => { delete s.coreManualLevels.planet_drive; },
    (s) => { delete s.coreHelperEnabled; },
    (s) => { s.coreAutoUnlocked.push("planet_drive"); },
    (s) => { s.coreManualLevels.planet_drive = 99; },
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
    const { engine, result } = replayGalaxy(data, { profile, coreHelper: true, days: 180 });
    assert.equal(result.completedPlanets, data.prestige.galaxyTargetPlanets);
    assert.ok(result.elapsedDays > 40 && result.elapsedDays < 180);
    assert.equal(result.stages.at(-1).thresholdSeconds, 1);
    assert.ok(result.stages.at(-1).seconds <= 1);
    // 重编航程只会发生在"买了一级永久科技"的时刻，与 2728 万颗星球的颗数无关
    assert.ok(result.compiled <= data.prestige.upgrades.reduce((n, spec) => n + spec.maxLevel, 0), String(result.compiled));
    assert.equal(result.research.length, data.prestige.upgrades.reduce((n, spec) => n + spec.maxLevel, 0));
    assert.ok(result.productiveTailDays >= 5 && result.productiveTailDays < 5.02);
    assert.ok(result.researchComplete.planets < result.completedPlanets);
    assert.deepEqual(new S2Engine(data, { state: engine.snapshot() }).snapshot(), engine.snapshot());
  }
});

test("burst is integrated only during the first second, including a purchase inside that second", () => {
  const e = fixture({ resets: burstResets });
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

  const late = fixture({ resets: burstResets });
  // 同样把时钟归零：解锁门槛推后到数百万颗之后，分钟数本身会大到吃掉双精度的末位，
  // 而本用例检验的是「这一秒之内」的积分。
  late.state.minute = 0; late.state.planetStartedMinute = 0;
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
  const e = fixture({ resets: burstResets });
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

test("research has value in its intended phase and burst changes from marginal to dominant", () => {
  const full = fixture({ resets: 500000, maxed: true });
  const duration = plan(full).duration;
  const together = new S2Engine(data, { state: full.snapshot() });
  let checked = 0;
  for (const spec of data.prestige.upgrades) {
    if (spec.effectKind === "completion_depth") continue;
    // 夹具买不起的科技（造价超过 50 万颗星球的理论总产出）不在本用例射程内
    if (full.state.coreLevels[spec.key] === 0) continue;
    const reduced = new S2Engine(data, { state: full.snapshot() });
    reduced.state.coreLevels[spec.key] -= 1;
    // 终局航程被「大爆发」和最短航程压得很扁，单项只要求"仍然算数"，
    // 真正的量级由下面按阶段的几条断言盯住。
    assert.ok(plan(reduced).duration > duration, spec.key);
    together.state.coreLevels[spec.key] -= 1;
    checked += 1;
  }
  assert.ok(checked >= 60, String(checked));
  // 合起来看就不是零头了：每项各退一级，终局航程要慢上好几倍
  assert.ok(plan(together).duration / duration > 2, String(plan(together).duration / duration));
  const finisher = fixture({ resets: 100 });
  const unfinishedDuration = plan(finisher).duration;
  finisher.purchaseCore("planetary_exhaustion");
  assert.ok(unfinishedDuration / plan(finisher).duration > 1.05);
  assert.equal(finisher.coreSpecs.planetary_exhaustion.maxLevel, 3, "early specialist ends cheaply rather than pretending to scale late");
  const early = fixture({ resets: burstResets });
  const baseline = plan(early).duration;
  early.purchaseCore("big_bang");
  const earlyGain = baseline / plan(early).duration;
  assert.ok(earlyGain > 1 && earlyGain < 1.001, String(earlyGain));
  // 「大爆发」要 230 万颗才解锁，50 万颗的夹具里还是 0 级；这里显式摆到满级看终局的分量：
  // 它一项就顶整条二阶段研究线的九倍以上，这是"压轴科技"的设计意图。
  assert.equal(full.state.coreLevels.big_bang, 0);
  const burst = new S2Engine(data, { state: full.snapshot() });
  burst.state.coreLevels.big_bang = full.coreSpecs.big_bang.maxLevel;
  const lateGain = duration / plan(burst).duration;
  assert.ok(lateGain > 9, String(lateGain));
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

test("the first departures stay in the player's hands, then the voyage automates itself", () => {
  const quota = Number(data.rules.manualDepartures);
  assert.ok(quota >= 1);
  const e = new S2Engine(data);
  e.state.autoDepart = true;
  for (let planet = 1; planet <= quota + 1; planet += 1) {
    e.state.depth = e.state.targetDepth;
    e.finishPlanet();
    const automated = planet > quota;
    assert.equal(e.autoDepartReady(), automated, `planet ${planet}`);
    // 配额用完之前，时间照常流动，但星球不会自己翻篇。
    const before = e.state.resets;
    e.mineBlock(1440);
    assert.equal(e.state.resets, automated ? before + 1 : before, `planet ${planet} resets`);
    assert.equal(e.state.planetComplete, !automated, `planet ${planet} parked`);
    if (!automated) assert.equal(e.departPlanet().ok, true);
  }
  // 教学期恰好覆盖第一个星区，走完就能拿到奖励核心并自己跑下去。
  assert.equal(data.prestige.sectors[0].targetPlanets, quota);
  assert.equal(e.autoDepartReady(), true);
});

test("permanent research follows the local rule: three hand-built levels, then the auto line takes over", () => {
  const commission = Number(data.prestige.coreCommissionLevels);
  const e = new S2Engine(voyageData);
  e.setCoreHelperEnabled(false);
  e.state.completedPlanets = e.state.resets = 20;
  e.state.cores = 1000;
  const key = "planet_drive";
  for (let i = 1; i <= commission; i += 1) {
    const bought = e.purchaseCore(key);
    assert.equal(bought.ok, true, `hand level ${i}`);
    assert.equal(bought.source, "manual");
    assert.equal(bought.commissioned, i === commission);
    assert.equal(e.coreCommissioned(key), i === commission);
  }
  // 够级之后手动渠道关闭，改由自动线接手
  assert.deepEqual(e.purchaseCore(key), { ok: false, reason: "locked" });
  const auto = e.autoPurchaseCore();
  assert.ok(auto.length > 0);
  assert.ok(auto.every((item) => item.key === key && item.source === "auto"));
  assert.equal(e.state.coreManualLevels[key], commission);

  // 夜班助手关着的时候，没转自动的科技一枚核心都不会动
  const idle = new S2Engine(voyageData);
  idle.setCoreHelperEnabled(false);
  idle.state.completedPlanets = idle.state.resets = 20; idle.state.cores = 1000;
  assert.deepEqual(idle.autoPurchaseCore(), []);
  assert.equal(idle.state.cores, 1000);

  // 打开助手：它会从最便宜的开始买，并且替玩家凑够那前几级
  const helped = new S2Engine(voyageData);
  helped.state.completedPlanets = helped.state.resets = 20; helped.state.cores = 1000;
  const bought = helped.setCoreHelperEnabled(true);
  assert.ok(bought.length > 0);
  assert.ok(bought.every((item) => item.source === "helper" || item.source === "auto"));
  assert.ok(helped.state.cores < 1000);
  const costs = bought.map((item) => item.cost);
  assert.deepEqual(costs, [...costs].sort((a, b) => a - b), "helper always buys the cheapest level first");
  assert.ok(helped.state.coreAutoUnlocked.length > 0, "cheap technologies reach the auto line on their own");
});
