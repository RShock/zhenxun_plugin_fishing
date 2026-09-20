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
const activeUpgrades = data.upgrades.filter((item) => item.status === "active");
const legacyActiveKeys = new Set(legacyData.upgrades.filter((item) => item.status === "active").map((item) => item.key));
const d11Upgrades = activeUpgrades.filter((item) => !legacyActiveKeys.has(item.key));
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
    assert.ok(large.state.totalHelperLevels > start.state.totalHelperLevels);
    assert.ok(Number.isFinite(large.state.depth));
    assert.ok(large.state.credits >= 0);
  }
});
