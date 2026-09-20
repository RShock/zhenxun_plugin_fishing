import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { runReplay, S2Engine, validateGameData } from "../../../../web/static/s2-vnext/engine.js";

const data = JSON.parse(await readFile(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url), "utf8"));
const pluginRoot = fileURLToPath(new URL("../../../../", import.meta.url));
const legacyData = JSON.parse(execFileSync(
  "git", ["show", "25f9313:web/static/s2-vnext/game_data.json"],
  { cwd: pluginRoot, encoding: "utf8" },
));
const clonedData = () => structuredClone(data);
const keyFor = (kind) => data.upgrades.find((item) => item.effectKind === kind)?.key;

function factorEngine() {
  const engine = new S2Engine(data, { seed: 42 });
  engine.state.depth = 1e12;
  engine.state.minute = 1440 + 240;
  engine.state.levels[keyFor("parallel")] = 2;
  engine.state.levels[keyFor("cats")] = 2;
  engine.state.levels[keyFor("speed_compound")] = 2;
  engine.state.levels[keyFor("momentum")] = 2;
  engine.state.levels[keyFor("fragility")] = 2;
  engine.state.levels[keyFor("crit_chance")] = 16;
  engine.state.levels[keyFor("crit_damage")] = 2;
  engine.state.levels[keyFor("penetration")] = 2;
  engine.state.levels[keyFor("pressure")] = 2;
  engine.state.autoUnlocked = data.upgrades
    .filter((item) => item.status === "active")
    .slice(0, 6)
    .map((item) => item.key);
  return engine;
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

test("late effect kinds have real per-level gains on every multiplier they target", () => {
  const targets = {
    network: ["incomeMultiplier", "depthMultiplier"],
    heat: ["incomeMultiplier"],
    cascade: ["incomeMultiplier", "depthMultiplier"],
    precision: ["incomeMultiplier", "depthMultiplier"],
    compression: ["depthMultiplier"],
    lens: ["depthMultiplier"],
  };
  for (const [kind, methods] of Object.entries(targets)) {
    const key = keyFor(kind);
    assert.ok(key, `missing ${kind} fixture`);
    const maxLevel = data.upgrades.find((item) => item.key === key).maxLevel;
    const engine = factorEngine();
    let previous = Object.fromEntries(methods.map((method) => [method, engine[method]()]));
    for (let level = 1; level <= maxLevel; level += 1) {
      engine.state.levels[key] = level;
      const current = Object.fromEntries(methods.map((method) => [method, engine[method]()]));
      methods.forEach((method) => assert.ok(current[method] > previous[method], `${kind} L${level} must improve ${method}`));
      previous = current;
    }
  }
});

test("late factor formulas preserve their specified cross-factor interactions", () => {
  const engine = factorEngine();
  for (const kind of ["network", "heat", "cascade", "precision", "compression", "lens"]) {
    engine.state.levels[keyFor(kind)] = 1;
  }
  const effects = engine.effectLevels();
  const factors = engine.multiplierBreakdown();
  assert.ok(Math.abs(factors.network - (1 + effects.network * Math.sqrt(factors.parallel * factors.cats))) < 1e-12);
  assert.ok(Math.abs(factors.heat - (1 + effects.heat * (factors.momentum + Math.log10(factors.speed)))) < 1e-12);
  const cascade = data.eras.reduce((product, era) => {
    const active = data.upgrades.filter((item) => item.era === era.key && item.status === "active");
    if (!active.length) return product;
    const automated = active.filter((item) => engine.state.autoUnlocked.includes(item.key)).length;
    return product * (1 + effects.cascade * automated / active.length);
  }, 1);
  assert.ok(Math.abs(factors.cascade - cascade) < 1e-12);
  assert.ok(Math.abs(factors.precision - (1 + effects.precision * factors.fragility * factors.critical
    * (1 + Math.max(0, effects.crit_chance - 0.65)))) < 1e-12);
  assert.ok(Math.abs(factors.compression - (1 + effects.compression * Math.sqrt(factors.penetration * factors.pressure))) < 1e-12);
  assert.ok(Math.abs(factors.lens - (1 + effects.lens * Math.log10(1 + engine.state.depth) / 10 * factors.compression)) < 1e-12);
});

test("route classifications include both, income-only and depth-only late effects", () => {
  const configured = (preferredKind) => {
    const copy = clonedData();
    copy.upgrades.forEach((item) => { item.status = "reserve"; });
    const kinds = [preferredKind, "heat", "compression"];
    const keys = kinds.map((kind) => copy.upgrades.find((item) => item.effectKind === kind).key);
    keys.forEach((key) => {
      const spec = copy.upgrades.find((item) => item.key === key);
      spec.status = "active"; spec.era = copy.eras[0].key; spec.unlockDepth = 0; spec.prerequisites = []; spec.baseCost = 1;
    });
    copy.strategy.priority = keys;
    const engine = new S2Engine(copy, { seed: 42 });
    engine.state.credits = 10;
    return { engine, keys };
  };
  for (const kind of ["network", "cascade", "precision"]) {
    const { engine, keys } = configured(kind);
    assert.equal(engine.chooseUpgrade("depth"), keys[0]);
    assert.equal(engine.chooseUpgrade("income"), keys[0]);
  }
  const { engine, keys } = configured("network");
  engine.data.strategy.priority = [keys[1], keys[2], keys[0]];
  engine.priority = [...engine.data.strategy.priority];
  assert.equal(engine.chooseUpgrade("income"), keys[1]);
  assert.equal(engine.chooseUpgrade("depth"), keys[2]);
});

test("active effects must be implemented while reserve effects may be unknown", () => {
  const active = clonedData();
  active.upgrades[0].effectKind = "future_unknown";
  assert.throws(() => validateGameData(active), /Unsupported active effect/);
  active.upgrades[0].status = "reserve";
  assert.doesNotThrow(() => validateGameData(active));
});

test("restore fills only thirty-day keys without mutating or replaying the old save", () => {
  const oldEngine = new S2Engine(data, { seed: 42 });
  oldEngine.mineBlock(1430);
  const payload = oldEngine.snapshot();
  const addedKeys = data.upgrades.filter((item) => item.addedIn === "thirty-day").map((item) => item.key);
  assert.equal(addedKeys.length, 13);
  addedKeys.forEach((key) => {
    delete payload.state.levels[key];
    delete payload.state.manualLevels[key];
  });
  delete payload.state.contentVersion;
  const originalPayload = structuredClone(payload);
  const restored = new S2Engine(data, { state: payload });
  assert.deepEqual(payload, originalPayload);
  addedKeys.forEach((key) => {
    assert.equal(restored.state.levels[key], 0);
    assert.equal(restored.state.manualLevels[key], 0);
  });
  for (const item of data.upgrades.filter((upgrade) => upgrade.addedIn !== "thirty-day")) {
    assert.equal(restored.state.levels[item.key], originalPayload.state.levels[item.key]);
    assert.equal(restored.state.manualLevels[item.key], originalPayload.state.manualLevels[item.key]);
  }
  assert.equal(restored.state.contentVersion, data.contentVersion);
  assert.equal(restored.state.minute, originalPayload.state.minute);
  assert.equal(restored.state.credits, originalPayload.state.credits);
  assert.equal(restored.state.depth, originalPayload.state.depth);
  assert.deepEqual(restored.rng.snapshot(), originalPayload.rng);
  assert.equal(restored.state.nextHelperMinute, originalPayload.state.nextHelperMinute);
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

test("restore rejects missing new keys in current saves and one-sided legacy damage", () => {
  const addedKey = data.upgrades.find((item) => item.addedIn === "thirty-day").key;
  for (const contentVersion of [data.contentVersion, undefined, null, ""]) {
    const versioned = new S2Engine(data, { seed: 42 }).snapshot();
    versioned.state.contentVersion = contentVersion;
    delete versioned.state.levels[addedKey];
    delete versioned.state.manualLevels[addedKey];
    assert.throws(() => new S2Engine(data, { state: versioned }), /存档字段损坏/);
  }

  for (const field of ["levels", "manualLevels"]) {
    const legacyDamage = new S2Engine(data, { seed: 42 }).snapshot();
    delete legacyDamage.state.contentVersion;
    delete legacyDamage.state[field][addedKey];
    assert.throws(() => new S2Engine(data, { state: legacyDamage }), /存档字段损坏/);
  }
});

test("restore preserves complete legacy level pairs instead of overwriting them", () => {
  const addedKey = data.upgrades.find((item) => item.addedIn === "thirty-day").key;
  const legacy = new S2Engine(data, { seed: 42 }).snapshot();
  delete legacy.state.contentVersion;
  legacy.state.levels[addedKey] = 2;
  legacy.state.manualLevels[addedKey] = 1;
  const original = structuredClone(legacy);
  const restored = new S2Engine(data, { state: legacy });
  assert.deepEqual(legacy, original);
  assert.equal(restored.state.levels[addedKey], 2);
  assert.equal(restored.state.manualLevels[addedKey], 1);
});

test("fixed 25f9313 D10 save migrated to current data matches a fresh current-data D30 run", () => {
  const legacy = runReplay(legacyData, { days: 10, seed: 42, profile: "daily", route: "balanced" }).engine.snapshot();
  delete legacy.state.contentVersion;
  const migrated = new S2Engine(data, { state: legacy });
  advanceDaily(migrated, data, 20);

  const freshThirtyDays = runReplay(data, { days: 30, seed: 42, profile: "daily", route: "balanced" }).engine;
  const migratedSnapshot = migrated.snapshot();
  const freshSnapshot = freshThirtyDays.snapshot();
  delete migratedSnapshot.state.targetDepth;
  delete freshSnapshot.state.targetDepth;
  assert.deepEqual(migratedSnapshot.state, freshSnapshot.state);
  assert.deepEqual(migratedSnapshot.rng, freshSnapshot.rng);
});

test("first ten days preserve the previous economy and purchases across 80 profiles", () => {
  for (const seed of [1, 7, 42, 99, 2026]) {
    for (const route of ["balanced", "cheapest", "depth", "income"]) {
      for (const profile of ["daily", "absent", "active", "opportunity"]) {
        const options = { days: 10, seed, route, profile };
        const old = runReplay(legacyData, options);
        const current = runReplay(data, options);
        assert.equal(current.engine.state.depth, old.engine.state.depth);
        assert.equal(current.engine.state.credits, old.engine.state.credits);
        assert.deepEqual(current.events, old.events, `${seed}/${route}/${profile}`);
        assert.deepEqual(current.engine.rng.snapshot(), old.engine.rng.snapshot());
      }
    }
  }
});

test("thirty daily batch visits match single-level economics with only 29 commands", () => {
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
  const expected = replay.engine.snapshot();
  expected.state.totalManualCommands = 29;
  assert.deepEqual(engine.snapshot(), expected);
  assert.deepEqual(
    [engine.state.totalManualLevels, engine.state.totalHelperLevels, engine.state.totalAutoLevels],
    [84, 45, 191],
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
    assert.ok(large.state.totalHelperLevels > start.state.totalHelperLevels);
    assert.ok(Number.isFinite(large.state.depth));
    assert.ok(large.state.credits >= 0);
  }
});
