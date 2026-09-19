import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { S2Engine, runReplay } from "../../../../web/static/s2-vnext/engine.js";

const data = JSON.parse(await readFile(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url), "utf8"));
const fresh = () => new S2Engine(data, { seed: 42 });

test("one large absence equals settlement-sized advances, including all midnight events", () => {
  const large = fresh(); const small = fresh();
  large.mineBlock(4320);
  const events = [];
  for (let i = 0; i < 432; i++) {
    small.mineBlock(10);
    events.push(...small.lastBlockEvents);
  }
  assert.deepEqual(large.snapshot(), small.snapshot());
  assert.deepEqual(large.lastBlockEvents, events);
  assert.equal(large.state.day, 4);
  assert.equal(large.state.totalManualLevels, 0);
  assert.ok(large.state.totalHelperLevels > 0);
});

test("save reload before midnight preserves RNG, helper schedule and subsequent purchases", () => {
  const original = fresh();
  original.mineBlock(1430);
  const restored = new S2Engine(data, { state: JSON.parse(JSON.stringify(original.snapshot())) });
  original.mineBlock(2890); restored.mineBlock(2890);
  assert.deepEqual(original.snapshot(), restored.snapshot());
  assert.deepEqual(original.lastBlockEvents, restored.lastBlockEvents);
});

test("invalid saves fail before replacing the live state", () => {
  const engine = fresh();
  for (const damage of [
    (save) => { delete save.state.manualLevels; },
    (save) => { save.state.credits = null; },
    (save) => { save.state.nextHelperMinute = 0; },
    (save) => { save.state.autoUnlocked = ["unknown"]; },
    (save) => { save.state.manualLevels.rotary_pick = 3; },
    (save) => { save.state.lastHelperReport = { items: [null] }; },
    (save) => { save.rng.index = 900; },
    (save) => { save.rng.mt[0] = -1; },
  ]) {
    const before = engine.snapshot(); const broken = structuredClone(before);
    damage(broken);
    assert.throws(() => engine.restore(broken));
    assert.deepEqual(engine.snapshot(), before);
  }
});

test("batch validation is atomic and an affordable partial purchase is one command", () => {
  const engine = fresh(); engine.state.credits = 1e9;
  const before = engine.snapshot();
  for (const orders of [null, [], [["rotary_pick", true]], [["rotary_pick", 101]],
    [["rotary_pick", 1], ["unknown", 1]], [[["rotary_pick"], 1]]]) {
    assert.equal(engine.upgradeCommand(orders).reason, "invalid");
    assert.deepEqual(engine.snapshot(), before);
  }
  engine.state.credits = engine.costFor("rotary_pick") + 1;
  const result = engine.upgradeCommand([["rotary_pick", 3]]);
  assert.equal(result.ok, true);
  assert.equal(result.reason, "credits");
  assert.equal(result.purchases.length, 1);
  assert.equal(engine.state.totalManualCommands, 1);
});

test("disabled shifts leave reports but are never backfilled and consume no extra RNG", () => {
  const enabled = fresh(); const disabled = fresh();
  assert.throws(() => disabled.setHelperEnabled(1));
  disabled.setHelperEnabled(false);
  enabled.mineBlock(2880); disabled.mineBlock(2880);
  assert.deepEqual(enabled.rng.snapshot(), disabled.rng.snapshot());
  assert.deepEqual(disabled.state.lastHelperReport, { minute: 2880, levels: 0, spent: 0, items: [] });
  disabled.setHelperEnabled(true);
  disabled.mineBlock(10);
  assert.equal(disabled.state.totalHelperLevels, 0);
  disabled.mineBlock(1430);
  assert.ok(disabled.state.totalHelperLevels > 0);
  assert.equal(disabled.state.nextHelperMinute, 5760);
});

test("affordability epsilon cannot leave a negative balance or break save reload", () => {
  const engine = fresh();
  engine.state.credits = engine.costFor("rotary_pick") - 1e-10;
  assert.equal(engine.upgradeCommand([["rotary_pick", 1]]).ok, true);
  assert.equal(engine.state.credits, 0);
  assert.deepEqual(new S2Engine(data, { state: engine.snapshot() }).snapshot(), engine.snapshot());
});

test("ten daily batch previews do not mutate saves and reproduce the single-level replay", () => {
  const engine = fresh();
  const counts = [];
  for (let day = 0; day < 10; day++) {
    engine.mineBlock(1200);
    const before = engine.snapshot();
    const preview = new S2Engine(data, { state: before });
    const orders = [];
    for (let key = preview.chooseUpgrade(); key; key = preview.chooseUpgrade()) {
      preview.upgradeCommand([[key, 1]]);
      orders.push([key, 1]);
    }
    assert.deepEqual(engine.snapshot(), before);
    const result = engine.upgradeCommand(orders);
    assert.equal(result.purchases.length, orders.length);
    counts.push(result.purchases.length);
    engine.mineBlock(240);
  }
  assert.deepEqual(counts, [6, 2, 3, 3, 3, 3, 3, 3, 5, 3]);
  assert.equal(engine.state.totalManualCommands, 10);
  const replay = runReplay(data).engine;
  const actual = engine.snapshot(); const expected = replay.snapshot();
  expected.state.totalManualCommands = 10;
  assert.deepEqual(actual, expected);
  assert.deepEqual([engine.state.totalManualLevels, engine.state.totalHelperLevels, engine.state.totalAutoLevels], [34, 17, 79]);
});
