import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { descriptionParts, renderDescription } from "../../../../web/static/s2-vnext/description.js";
import { S2Engine } from "../../../../web/static/s2-vnext/engine.js";

const data = JSON.parse(await readFile(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url), "utf8"));
const active = data.upgrades.filter((spec) => spec.status === "active");
const regions = Object.fromEntries(data.multiplierRegions.map((region) => [region.key, region]));
const terms = new Set([
  "矿币收益", "挖矿深度", "自动线", "矿币价格",
  ...data.resources.map((resource) => resource.name),
  ...data.multiplierRegions.map((region) => region.name),
  ...active.map((spec) => spec.name),
  ...data.prestige.upgrades.map((spec) => spec.name),
]);

test("description parser preserves prose and recognizes only complete single-line bold spans", () => {
  assert.deepEqual(descriptionParts(""), []);
  assert.deepEqual(descriptionParts("增加**矿币收益**，不改变**挖矿深度**。"), [
    { strong: false, text: "增加" }, { strong: true, text: "矿币收益" },
    { strong: false, text: "，不改变" }, { strong: true, text: "挖矿深度" },
    { strong: false, text: "。" },
  ]);
  assert.deepEqual(descriptionParts("**矿币收益****挖矿深度**"), [
    { strong: true, text: "矿币收益" }, { strong: true, text: "挖矿深度" },
  ]);
  for (const text of ["普通说明", "**未闭合", "****", "**跨\n行**", "**跨\r行**", "*斜体*", "[链接](url)"]) {
    assert.deepEqual(descriptionParts(text), [{ strong: false, text }]);
  }
});

test("renderer creates only text and strong nodes, never interpreting HTML", () => {
  const createdTags = [];
  const element = {
    ownerDocument: {
      createTextNode: (textContent) => ({ nodeType: 3, textContent }),
      createElement: (tagName) => {
        createdTags.push(tagName);
        return { nodeType: 1, tagName, textContent: "" };
      },
    },
    replaceChildren(...children) { this.children = children; },
  };
  renderDescription(element, '<img src=x onerror="alert(1)">**<script>alert(2)</script>**');
  assert.deepEqual(createdTags, ["strong"]);
  assert.deepEqual(element.children, [
    { nodeType: 3, textContent: '<img src=x onerror="alert(1)">' },
    { nodeType: 1, tagName: "strong", textContent: "<script>alert(2)</script>" },
  ]);
  renderDescription(element, "新说明");
  assert.deepEqual(element.children, [{ nodeType: 3, textContent: "新说明" }]);
  renderDescription(element, "");
  assert.deepEqual(element.children, []);
});

test("all active descriptions explain both outcomes and reference real named concepts", () => {
  assert.equal(active.length, 43);
  for (const spec of active) {
    assert.ok(spec.description.includes("**矿币收益**"), spec.key);
    assert.ok(spec.description.includes("**挖矿深度**"), spec.key);
    assert.doesNotMatch(spec.description, /作业面|乘区|复乘|离线照常/, spec.key);
    for (const part of descriptionParts(spec.description)) {
      if (part.strong) assert.ok(terms.has(part.text), `${spec.key}: unknown term ${part.text}`);
      else assert.ok(!part.text.includes("**"), `${spec.key}: malformed markup`);
    }
  }
});

test("ordinary additive upgrades state the region increment, not a total production percentage", () => {
  const kinds = new Set(["parallel", "cats", "sharpness", "fragility", "income", "extra_depth"]);
  for (const spec of active.filter((item) => kinds.has(item.effectKind))) {
    assert.ok(spec.description.includes(`+${spec.effectPerLevel.toFixed(2)}`), spec.key);
    assert.ok(spec.description.includes("倍率"), spec.key);
    assert.ok(spec.description.includes("相加"), spec.key);
    assert.ok(!spec.description.includes("%"), spec.key);
  }
  for (const spec of active.filter((item) => item.effectKind === "speed_compound")) {
    assert.ok(spec.description.includes(`提高 ${Math.round(spec.effectPerLevel * 100)}%`), spec.key);
    const engine = new S2Engine(data);
    engine.state.levels[spec.key] = 2;
    const income = engine.incomeMultiplier(); const depth = engine.depthMultiplier();
    engine.state.levels[spec.key] += 1;
    assert.ok(Math.abs(engine.incomeMultiplier() / income - 1 - spec.effectPerLevel) < 1e-12);
    assert.ok(Math.abs(engine.depthMultiplier() / depth - 1 - spec.effectPerLevel) < 1e-12);
  }
  for (const spec of active.filter((item) => item.effectKind === "crit_chance")) {
    assert.ok(spec.description.includes(`${Math.round(spec.effectPerLevel * 100)} 个百分点`), spec.key);
    assert.ok(spec.description.includes("65%"), spec.key);
  }
});

test("permanent research references the same named concepts as local equipment", () => {
  for (const spec of data.prestige.upgrades) {
    for (const part of descriptionParts(spec.description)) {
      if (part.strong) assert.ok(terms.has(part.text), `${spec.key}: unknown term ${part.text}`);
      else assert.ok(!part.text.includes("**"), `${spec.key}: malformed markup`);
    }
  }
});

test("income-only and depth-only descriptions agree with actual upgrade effects", () => {
  for (const spec of active) {
    const scope = regions[spec.region].scope;
    if (!["income", "depth"].includes(scope)) continue;
    const engine = new S2Engine(data);
    engine.state.autoUnlocked = active.slice(0, 4).map((item) => item.key);
    for (const support of active.filter((item) => ["crit_chance", "crit_damage"].includes(item.effectKind))) {
      engine.state.levels[support.key] = 1;
    }
    const before = { income: engine.incomeMultiplier(), depth: engine.depthMultiplier() };
    engine.state.levels[spec.key] = 1;
    if (scope === "depth") {
      assert.match(spec.description, /不会?增加\*\*矿币收益\*\*/, spec.key);
      assert.equal(engine.incomeMultiplier(), before.income, spec.key);
      assert.ok(engine.depthMultiplier() > before.depth, spec.key);
    } else {
      assert.match(spec.description, /不(?:会增加|增加|影响)\*\*挖矿深度\*\*/, spec.key);
      assert.equal(engine.depthMultiplier(), before.depth, spec.key);
      assert.ok(engine.incomeMultiplier() > before.income, spec.key);
    }
  }
});

test("synergy descriptions name their real dependencies and do not promise faster purchasing", () => {
  for (const spec of active) {
    if (spec.effectKind === "coordination") {
      assert.ok(spec.description.includes("**猫矿工产能**类科技的累计等级"), spec.key);
    }
    if (["resonance", "shift_relay"].includes(spec.effectKind)) {
      assert.ok(spec.description.includes("**自动线**"), spec.key);
      assert.ok(spec.description.includes("全部**矿币收益**"), spec.key);
      assert.ok(regions[spec.region].note.includes("在本星完成调试且已实际建成"), spec.key);
      assert.doesNotMatch(spec.description, /三次调试/, spec.key);
    }
    if (spec.effectKind === "momentum") {
      assert.ok(spec.description.includes("抵达本星球"), spec.key);
      assert.ok(spec.description.includes("每 24 游戏小时"), spec.key);
      assert.ok(spec.description.includes("前 4 小时"), spec.key);
      assert.doesNotMatch(spec.description, /00:00|04:00/, spec.key);
      assert.ok(spec.description.includes("不需要手动维持"), spec.key);
    }
  }
});
