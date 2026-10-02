import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { runReplay, S2Engine, validateGameData } from "../../../../web/static/s2-vnext/engine.js";

const data = JSON.parse(await readFile(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url), "utf8"));
const clonedData = () => structuredClone(data);
const activeUpgrades = data.upgrades.filter((item) => item.status === "active");
// D11 之后补进来的那批设备在数据里自带 addedIn 标记；原先这里是跟一个历史提交（25f9313）
// 的 game_data.json 对比得出的，仓库改成浅克隆后那个对象取不到，而且那份旧数值早已被
// 后续几轮改动覆盖，对比本身也不再成立。
const d11Upgrades = activeUpgrades.filter((item) => item.addedIn === "thirty-day");
const legacyActiveKeys = new Set(activeUpgrades.filter((item) => item.addedIn !== "thirty-day").map((item) => item.key));
const regions = Object.fromEntries(data.multiplierRegions.map((item) => [item.key, item]));

function factorEngine() {
  const engine = new S2Engine(data, { seed: 42 });
  engine.state.depth = 1e30;
  engine.state.minute = 1440 + 240;
  engine.state.autoUnlocked = activeUpgrades.slice(0, 6).map((item) => item.key);
  for (const kind of ["coordination", "crit_chance", "crit_damage"]) {
    const support = activeUpgrades.find((item) => item.effectKind === kind);
    if (support) engine.state.levels[support.key] = 1;
  }
  return engine;
}

function expectedRegionFactor(engine, specs) {
  if (specs[0].region === "speed") {
    return specs.reduce(
      (product, spec) => product * (1 + Number(spec.effectPerLevel)) ** engine.level(spec.key),
      1,
    );
  }
  const total = specs.reduce(
    (sum, spec) => sum + Number(spec.effectPerLevel) * engine.level(spec.key),
    0,
  );
  if (specs[0].region === "momentum") {
    return 1 + total * Math.min(1, (engine.state.minute % 1440) / 240);
  }
  if (["resonance", "shift_relay"].includes(specs[0].region)) {
    return 1 + total * engine.state.autoUnlocked.length;
  }
  return 1 + total;
}

function advanceDaily(engine, replayData, days) {
  const checks = new Set(replayData.strategy.profiles.daily.checkMinutes.map(Number));
  for (let day = 0; day < days; day += 1) {
    for (let minute = Number(replayData.rules.settlementMinutes); minute <= 1440; minute += Number(replayData.rules.settlementMinutes)) {
      engine.mineBlock();
      if (checks.has(minute)) engine.strategyVisit("balanced");
    }
  }
}

test("every D11+ technology has a real per-level gain only in its configured scope", () => {
  assert.ok(d11Upgrades.length > 0);
  for (const spec of d11Upgrades) {
    const scope = regions[spec.region]?.scope;
    assert.ok(["both", "income", "depth"].includes(scope), `${spec.key} has invalid scope`);
    const engine = factorEngine();
    engine.state.levels[spec.key] = 0;
    let previous = {
      income: engine.incomeMultiplier(),
      depth: engine.depthMultiplier(),
    };
    for (let level = 1; level <= spec.maxLevel; level += 1) {
      engine.state.levels[spec.key] = level;
      const current = {
        income: engine.incomeMultiplier(),
        depth: engine.depthMultiplier(),
      };
      if (scope === "both" || scope === "income") {
        assert.ok(current.income > previous.income, `${spec.key} L${level} must improve income`);
      } else {
        assert.equal(current.income, previous.income, `${spec.key} L${level} must not affect income`);
      }
      if (scope === "both" || scope === "depth") {
        assert.ok(current.depth > previous.depth, `${spec.key} L${level} must improve depth`);
      } else {
        assert.equal(current.depth, previous.depth, `${spec.key} L${level} must not affect depth`);
      }
      previous = current;
    }
  }
});

test("same-region era handoffs add simply while speed technologies multiply independently", () => {
  let checked = 0;
  for (const newer of d11Upgrades) {
    const older = activeUpgrades.find((item) =>
      legacyActiveKeys.has(item.key) && item.region === newer.region && item.era !== newer.era);
    if (!older) continue;
    const engine = new S2Engine(data, { seed: 42 });
    engine.state.minute = 1440 + 240;
    engine.state.autoUnlocked = activeUpgrades.slice(0, 6).map((item) => item.key);
    engine.state.levels[older.key] = Math.min(2, older.maxLevel);
    engine.state.levels[newer.key] = Math.min(2, newer.maxLevel);
    const actual = engine.multiplierBreakdown()[newer.region];
    const expected = expectedRegionFactor(engine, [older, newer]);
    assert.ok(Math.abs(actual - expected) < 1e-12, `${older.key} -> ${newer.key}`);
    checked += 1;
  }
  assert.ok(checked > 0);
});

test("old technologies stop at max level and every later era requires depth plus prior automation", () => {
  const oldSpec = activeUpgrades.find((item) => legacyActiveKeys.has(item.key));
  assert.ok(oldSpec);
  const capped = new S2Engine(data, { seed: 42 });
  capped.state.depth = 1e30;
  capped.state.credits = 1e300;
  capped.state.levels[oldSpec.key] = oldSpec.maxLevel;
  capped.state.autoUnlocked = [oldSpec.key];
  assert.equal(capped.available(oldSpec.key), false);
  assert.equal(capped.available(oldSpec.key, true), false);
  assert.deepEqual(capped.purchase(oldSpec.key), { ok: false, reason: "locked" });
  assert.deepEqual(capped.purchase(oldSpec.key, true), { ok: false, reason: "locked" });

  for (let index = 1; index < data.eras.length; index += 1) {
    const era = data.eras[index];
    const previousEra = data.eras[index - 1].key;
    const previousKeys = activeUpgrades.filter((item) => item.era === previousEra).map((item) => item.key);
    const required = Number(era.previousEraAutomations);
    assert.ok(previousKeys.length >= required, `${era.key} lacks prior automation fixtures`);

    const engine = new S2Engine(data, { seed: 42 });
    engine.state.depth = Number(era.unlockDepth);
    engine.state.autoUnlocked = previousKeys.slice(0, Math.max(0, required - 1));
    assert.equal(engine.eraUnlocked(era.key), false, `${era.key} must require prior automation`);

    engine.state.depth = Number(era.unlockDepth) / 2;
    engine.state.autoUnlocked = previousKeys.slice(0, required);
    assert.equal(engine.eraUnlocked(era.key), false, `${era.key} must require depth`);

    engine.state.depth = Number(era.unlockDepth);
    assert.equal(engine.eraUnlocked(era.key), true, `${era.key} should unlock after both gates`);
  }
});

test("active effects must be implemented while reserve effects may be unknown", () => {
  const active = clonedData();
  active.upgrades[0].effectKind = "future_unknown";
  assert.throws(() => validateGameData(active), /Unsupported active effect/);
  active.upgrades[0].status = "reserve";
  assert.doesNotThrow(() => validateGameData(active));
});

test("restore still rejects missing pre-existing keys and invalid new-key values", () => {
  const old = new S2Engine(data, { seed: 42 }).snapshot();
  const addedKeys = data.upgrades.filter((item) => item.addedIn === "thirty-day").map((item) => item.key);
  addedKeys.forEach((key) => {
    delete old.state.levels[key];
    delete old.state.manualLevels[key];
  });
  const missingOld = structuredClone(old);
  delete missingOld.state.levels[data.upgrades[0].key];
  assert.throws(() => new S2Engine(data, { state: missingOld }), /存档字段损坏/);
  const invalidNew = structuredClone(old);
  invalidNew.state.levels[addedKeys[0]] = -1;
  assert.throws(() => new S2Engine(data, { state: invalidNew }), /存档字段损坏/);
});

test("restore rejects current saves that are missing any equipment key", () => {
  const addedKey = data.upgrades.find((item) => item.addedIn === "thirty-day").key;
  for (const field of ["levels", "manualLevels"]) {
    const damaged = new S2Engine(data, { seed: 42 }).snapshot();
    delete damaged.state[field][addedKey];
    assert.throws(() => new S2Engine(data, { state: damaged }), /存档字段损坏/);
  }
  // 旧版存档（contentVersion 对不上）一律整份拒绝；迁移已于 2026-10-02 取消
  for (const contentVersion of [undefined, null, "", "thirty-day-eras-1"]) {
    const versioned = new S2Engine(data, { seed: 42 }).snapshot();
    versioned.state.contentVersion = contentVersion;
    assert.throws(() => new S2Engine(data, { state: versioned }));
  }
});

test("thirty daily batch visits match replay economics and count only nonempty visits", () => {
  const engine = new S2Engine(data, { seed: 42 });
  const counts = [];
  for (let day = 0; day < 30; day++) {
    engine.mineBlock(1200);
    const before = engine.snapshot();
    const preview = new S2Engine(data, { state: before });
    const orders = [];
    for (let key = preview.chooseUpgrade(); key; key = preview.chooseUpgrade()) {
      preview.upgradeCommand([[key, 1]]);
      orders.push([key, 1]);
    }
    assert.deepEqual(engine.snapshot(), before);
    if (orders.length) {
      const result = engine.upgradeCommand(orders);
      assert.equal(result.purchases.length, orders.length);
      assert.equal(engine.chooseUpgrade(), null);
    }
    counts.push(orders.length);
    engine.mineBlock(240);
  }
  const replay = runReplay(data, { days: 30 });
  assert.deepEqual(counts, replay.snapshots.map((day) => day.manualLevels));
  const commandDays = counts.filter((count) => count > 0).length;
  const expected = replay.engine.snapshot();
  expected.state.totalManualCommands = commandDays;
  assert.deepEqual(engine.snapshot(), expected);
  assert.equal(engine.state.totalManualCommands, commandDays);
  assert.deepEqual(
    [engine.state.totalManualLevels, engine.state.totalHelperLevels, engine.state.totalAutoLevels],
    [replay.engine.state.totalManualLevels, replay.engine.state.totalHelperLevels, replay.engine.state.totalAutoLevels],
  );
});

test("three-day late absence survives JSON reload and matches settlement-sized steps", () => {
  for (const day of [10, 20, 27]) {
    const start = runReplay(data, { days: day }).engine.snapshot();
    const large = new S2Engine(data, { state: JSON.parse(JSON.stringify(start)) });
    const small = new S2Engine(data, { state: start });
    large.mineBlock(4320);
    const events = [];
    for (let i = 0; i < 432; i++) {
      small.mineBlock(10);
      events.push(...small.lastBlockEvents);
    }
    assert.deepEqual(large.snapshot(), small.snapshot());
    assert.deepEqual(large.lastBlockEvents, events);
    // 笨助手只补"还没转自动"的设备：教学期前段它天天有活干，到 D20 之后
    // 该转自动的都转了（首星 D23 全满），它自然就闲下来，不能再要求它一直涨。
    assert.ok(large.state.totalHelperLevels >= start.state.totalHelperLevels, `helper day ${day}`);
    assert.ok(large.state.totalAutoLevels >= start.state.totalAutoLevels, `auto day ${day}`);
    if (day === 10) assert.ok(large.state.totalHelperLevels > start.state.totalHelperLevels);
    assert.ok(Number.isFinite(large.state.depth));
    assert.ok(large.state.credits >= 0);
  }
});
