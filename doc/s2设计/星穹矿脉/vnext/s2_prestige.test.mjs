import assert from "node:assert/strict";
import fs from "node:fs";
import { createHash } from "node:crypto";
import test from "node:test";
import { S2Engine, runReplay, validateGameData } from "../../../../web/static/s2-vnext/engine.js";
import { replayPrestige } from "./s2_prestige_replay.mjs";

const data = JSON.parse(fs.readFileSync(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url)));
const fresh = () => new S2Engine(data);
const daily = replayPrestige(data);
const absent = replayPrestige(data, { profile: "absent", days: 600 });
function nearTree(a, b) {
  if (typeof a === "number" && typeof b === "number") {
    assert.ok(Math.abs(a - b) <= 2e-7 + Math.max(Math.abs(a), Math.abs(b)) * 2e-10, `${a} != ${b}`);
  } else if (a && b && typeof a === "object" && typeof b === "object") {
    assert.deepEqual(Object.keys(a).sort(), Object.keys(b).sort());
    for (const key of Object.keys(a)) nearTree(a[key], b[key]);
  } else assert.deepEqual(a, b);
}
// 这些用例盯的是"换星结构"（奖励只发一次、换星清空本地、核心科技的作用域），
// 而永久科技的夜班助手会在后台花掉核心、改写这些数字，所以这里显式关掉它；
// 助手本身的行为由 s2_voyage.test.mjs 的专门用例和下面的 absent 回放覆盖。
function completedFirst() {
  return runReplay(data, { days: 45, profile: "absent", coreHelper: false }).engine;
}
// 从等级反推"这些永久科技一共花掉了多少核心"
function coreSpent(e) {
  return Object.values(e.coreSpecs).reduce((sum, spec) => {
    let total = 0;
    for (let i = 0; i < e.state.coreLevels[spec.key]; i += 1) total += spec.baseCost * spec.costGrowth ** i;
    return sum + total;
  }, 0);
}

test("the approved first thirty days stay pinned to the recorded baseline", () => {
  const baseline = JSON.parse(fs.readFileSync(new URL("./thirty_days_baseline.json", import.meta.url)));
  assert.deepEqual(Object.keys(baseline.profiles).sort(), ["absent", "active", "daily", "low", "regular"]);
  for (const [profile, expected] of Object.entries(baseline.profiles)) {
    const run = runReplay(data, { days: 30, profile });
    assert.equal(run.engine.state.credits, expected.credits, profile);
    assert.equal(run.engine.state.depth, expected.depth, profile);
    assert.equal(run.events.length, expected.events, profile);
    assert.equal(createHash("sha256").update(JSON.stringify(run.events)).digest("hex"), expected.eventsHash, profile);
    // 随机数发生器的内部状态（624 个整数）只存指纹，免得基线文件变成一坨噪音
    assert.equal(createHash("sha256").update(JSON.stringify(run.engine.rng.snapshot())).digest("hex"), expected.rngHash, profile);
    // 教学期的终点（第一颗星球挖没挖穿、核心剩几枚）同样钉死
    assert.equal(run.engine.state.completedPlanets, expected.completedPlanets, profile);
    assert.equal(run.engine.state.cores, expected.cores, profile);
  }
});

test("first planet still mines for about three days after every upgrade is maxed", () => {
  for (const replay of [daily, absent]) {
    const first = replay.milestones[0];
    const tail = (first.completedMinute - first.allMaxedMinute) / 1440;
    // 一阶段在 2026-10-01 那轮被压缩（首星 D39→D28）之后，"升满之后还要再挖一阵"
    // 这条设计意图保留，但量级从约五天变成约三天；五天的时间墙现在只在银河终局。
    assert.ok(tail >= 2.5 && tail <= 3.5, String(tail));
    assert.equal(first.reward, 1);
  }
  assert.ok(daily.milestones[0].minutes < absent.milestones[0].minutes);
});

test("completion awards exactly once, freezes local activity, and waits for the first departure", () => {
  const e = completedFirst();
  assert.equal(e.state.planetComplete, true);
  assert.equal(e.state.completedPlanets, 1);
  assert.equal(e.state.resets, 0);
  assert.equal(e.state.cores, 1);
  const snapshot = e.snapshot();
  e.mineBlock(4320);
  assert.equal(e.state.cores, 1);
  assert.equal(e.state.depth, data.prestige.planetTargetDepth);
  assert.equal(e.state.credits, snapshot.state.credits);
  assert.deepEqual(e.state.levels, snapshot.state.levels);
  assert.deepEqual(e.rng.snapshot(), snapshot.rng);
  assert.equal(e.finishPlanet(), false);
  assert.equal(e.upgradeCommand([["rotary_pick", 1]]).ok, false);
  assert.equal(e.state.planetHistory.length, 1);
  assert.deepEqual(new S2Engine(data, { state: e.snapshot() }).snapshot(), e.snapshot());
});

test("departure clears every local upgrade and balance but retains purchased core technology and lifetime counters", () => {
  const e = completedFirst();
  assert.equal(e.purchaseCore("core_drill").ok, true);
  const before = e.snapshot();
  assert.equal(e.departPlanet().ok, true);
  assert.equal(e.departPlanet().ok, false);
  assert.equal(e.state.credits, 0);
  assert.equal(e.state.depth, 0);
  assert.ok(Object.values(e.state.levels).every((v) => v === 0));
  assert.ok(Object.values(e.state.manualLevels).every((v) => v === 0));
  assert.deepEqual(e.state.autoUnlocked, []);
  assert.deepEqual(e.state.everKeys, []);
  assert.deepEqual(e.state.eraFirstDays, {});
  assert.equal(e.state.lastHelperReport, null);
  assert.equal(e.state.allMaxedMinute, null);
  assert.equal(e.state.planetStartedMinute, e.state.minute);
  assert.equal(e.state.coreLevels.core_drill, 1);
  assert.equal(e.state.totalAutoLevels, before.state.totalAutoLevels);
  assert.equal(e.state.nextAutoMinute, before.state.nextAutoMinute);
  assert.equal(e.state.nextHelperMinute, before.state.nextHelperMinute);
  assert.equal(e.manualTarget("rotary_pick"), 2);
  assert.equal(e.incomeMultiplier(), 1);
  assert.equal(e.depthMultiplier(), 1);
  assert.deepEqual(e.rng.snapshot(), before.rng);
  assert.deepEqual(new S2Engine(data, { state: e.snapshot() }).snapshot(), e.snapshot());
});

test("zero commissioning does not grant imaginary lines, prerequisites, or free equipment", () => {
  const e = fresh(); e.state.resets = 3;
  // 本用例检验的是「零调试不会凭空送设备」。开局 300 矿币是另一条规则，
  // 会让第一次自动采购立刻买得起手工矿镐，因此先把它花掉的前提排除掉。
  e.state.credits = 0;
  assert.equal(e.manualTarget("rotary_pick"), 0);
  assert.deepEqual(e.state.autoUnlocked, []);
  assert.equal(e.available("rotary_pick"), false);
  assert.equal(e.available("rotary_pick", true), true);
  assert.equal(e.eraUnlocked("industrial"), false);
  assert.deepEqual(e.autoPurchase(), []);
  e.state.credits = e.costFor("rotary_pick");
  assert.equal(e.autoPurchase().length, 1);
  assert.equal(e.level("rotary_pick"), 1);
  assert.equal(e.state.credits, 0);
  assert.ok(e.state.autoUnlocked.includes("rotary_pick"));
  assert.equal(e.state.manualLevels.rotary_pick, 0);
  assert.equal(e.state.totalManualLevels, 0);
});

test("core investments accelerate voyages, and the night-shift helper carries fully absent players too", () => {
  for (const replay of [daily, absent]) {
    assert.equal(replay.milestones.length, 12);
    const rows = replay.milestones;
    // 规则变更（2026-10-02）：永久科技的夜班助手默认开着，所以连一次都不操作的玩家
    // 也会越挖越快——过去那条"第 4 颗以后每颗都一样长"的停滞平台已经取消。
    assert.ok(rows.at(-1).minutes < rows[0].minutes / 20, String(rows.at(-1).minutes / rows[0].minutes));
    assert.ok(rows.at(-1).minutes < rows[3].minutes, String(rows.at(-1).minutes));
    for (const row of rows.slice(3)) assert.equal(row.totalManualLevels, rows[2].totalManualLevels);
    assert.ok(replay.engine.state.maxDailyManualLevels <= 12);
    assert.deepEqual(new S2Engine(data, { state: replay.engine.snapshot() }).snapshot(), replay.engine.snapshot());
  }
  // 本地设备一换星就清零，所以第 12 颗的航程只能由永久科技决定：
  // 天天上线的人和完全托管的人走到这里时，永久科技的进度是一样的。
  nearTree(daily.milestones.at(-1).minutes, absent.milestones.at(-1).minutes);
  assert.equal(absent.engine.state.totalManualLevels, 0);
  assert.equal(absent.engine.state.totalManualCommands, 0);
  // 核心守恒：12 颗星球的理论收入 21 枚，加上星区阶段奖励（启明星区 +3、猎户支臂 +12），
  // 一枚不多一枚不少，要么还在手上，要么变成了永久科技的等级。
  for (const replay of [daily, absent]) {
    assert.equal(replay.engine.state.cores + coreSpent(replay.engine), 21 + 3 + 12);
    assert.ok(replay.engine.state.cores >= 0);
  }
});

test("large advances and save/reload remain identical across many planet boundaries", () => {
  const start = daily.engine.snapshot();
  const large = new S2Engine(data, { state: start });
  let small = new S2Engine(data, { state: start });
  large.mineBlock(4320);
  const events = [];
  for (let i = 0; i < 432; i += 1) {
    small.mineBlock();
    events.push(...small.lastBlockEvents);
    if (i % 11 === 0) small = new S2Engine(data, { state: JSON.parse(JSON.stringify(small.snapshot())) });
  }
  nearTree(large.snapshot(), small.snapshot());
  // Full repeated cycles report aggregate counts, not an unbounded event array.
  assert.ok(large.lastBlockEvents.length <= 1024);
  assert.ok(large.state.completedPlanets > start.state.completedPlanets);
  assert.equal(large.state.planetHistory.length, Math.min(large.state.completedPlanets, data.prestige.historyLimit));
  assert.ok(Number.isFinite(large.incomeMultiplier()));
});

test("disabled automatic departure keeps the next completion parked with its core intact", () => {
  const e = new S2Engine(data, { state: daily.engine.snapshot() });
  assert.throws(() => e.setAutoDepart(1));
  e.setAutoDepart(false);
  const before = e.state.completedPlanets;
  e.mineBlock(1440);
  assert.equal(e.state.completedPlanets, before + 1);
  assert.equal(e.state.resets, before);
  const cores = e.state.cores;
  e.mineBlock(1440);
  assert.equal(e.state.cores, cores);
  assert.equal(e.state.completedPlanets, before + 1);
  e.setAutoDepart(true); e.mineBlock(10);
  assert.equal(e.state.resets, before + 1);
  assert.ok(e.state.depth > 0, "the ten-minute remainder now actually mines the next planet");
});

test("core purchases preserve scope and amplify rebuilt equipment instead of preserving old levels", () => {
  const e = completedFirst();
  const before = e.snapshot();
  for (const key of ["unknown", "stellar_forge", "core_refining"]) assert.equal(e.purchaseCore(key).ok, false);
  assert.deepEqual(e.snapshot(), before);
  assert.equal(e.purchaseCore("core_drill").ok, true);
  assert.equal(e.purchaseCore("core_drill").ok, false);
  e.departPlanet(); e.state.credits = 1e8;
  e.purchase("rotary_pick");
  const spec = e.specs.rotary_pick;
  assert.equal(e.multiplierBreakdown().speed, 1 + spec.effectPerLevel * (1 + e.coreSpecs.core_drill.effectPerLevel));
  for (const [key, kind, otherKind] of [["core_refining", "income", "extra_depth"], ["core_depth", "extra_depth", "income"]]) {
    const f = fresh(); f.state.coreLevels[key] = 1;
    assert.equal(f.effectStrength(kind), 1.5);
    assert.equal(f.effectStrength(otherKind), 1);
  }
  const f = fresh(); f.state.coreLevels.stellar_forge = 1;
  assert.equal(f.effectStrength("crit_chance"), 1);
  assert.equal(f.effectStrength("parallel"), 1.2);
});

test("local age effects restart on the new planet rather than inheriting the universe age", () => {
  const old = fresh(); const young = fresh();
  for (const spec of data.upgrades.filter((spec) => ["teamwork", "momentum"].includes(spec.effectKind))) {
    old.state.levels[spec.key] = young.state.levels[spec.key] = 2;
  }
  old.state.minute = 60000; old.state.planetStartedMinute = 59900;
  young.state.minute = 100;
  assert.equal(old.multiplierBreakdown().teamwork, young.multiplierBreakdown().teamwork);
  assert.equal(old.multiplierBreakdown().momentum, young.multiplierBreakdown().momentum);
});

test("a damaged prestige save fails atomically instead of half-loading", () => {
  const e = runReplay(data, { days: 30 }).engine;
  const saved = e.snapshot();
  for (const damage of [
    (s) => { delete s.state.cores; }, (s) => { s.state.cores = 1; },
    (s) => { s.state.resets = 1; }, (s) => { s.state.coreLevels.core_drill = 100; },
    (s) => { delete s.state.coreManualLevels; }, (s) => { s.state.coreManualLevels.core_drill = 99; },
    (s) => { s.state.coreAutoUnlocked = ["core_drill"]; }, (s) => { s.state.coreHelperEnabled = "yes"; },
    // D30 的存档本身已经挖穿第一颗星球，所以这里反过来篡改：谎称"还没挖穿"
    (s) => { s.state.planetComplete = false; }, (s) => { s.state.planetComplete = "yes"; },
    (s) => { s.state.autoDepart = 1; },
    (s) => { s.state.planetHistory = [null]; }, (s) => { s.state.planetStartedMinute = s.state.minute + 10; },
    (s) => { s.state.targetDepth = 1; }, (s) => { s.state.contentVersion = "unknown"; },
    // 旧版存档（迁移已于 2026-10-02 随五路线托管一起取消）同样整份拒绝，不做半吊子兼容
    (s) => { s.state.contentVersion = "thirty-day-eras-1"; },
  ]) {
    const broken = structuredClone(saved); damage(broken);
    assert.throws(() => e.restore(broken)); assert.deepEqual(e.snapshot(), saved);
  }
});
test("legacy fully upgraded planets keep an unknown full-upgrade timestamp", () => {
  const saved = completedFirst().snapshot();
  saved.state.allMaxedMinute = null;
  saved.state.planetHistory[0].allMaxedMinute = null;
  const e = new S2Engine(data, { state: saved });
  e.mineBlock(1440);
  assert.equal(e.state.allMaxedMinute, null);
  assert.equal(e.state.planetHistory[0].allMaxedMinute, null);
});

test("prestige configuration rejects malformed currencies, unknown effects and unbounded costs", () => {
  for (const damage of [
    (d) => { d.resources.pop(); }, (d) => { delete d.prestige; },
    (d) => { d.prestige.planetTargetDepth = -1; },
    (d) => { d.prestige.upgrades[0].effectKind = "unimplemented"; },
    (d) => { d.prestige.upgrades[0].maxLevel = 10000; },
    (d) => { d.prestige.upgrades[0].costGrowth = 1e12; },
  ]) {
    const bad = structuredClone(data); damage(bad); assert.throws(() => validateGameData(bad));
  }
});
