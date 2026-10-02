#!/usr/bin/env node
// S2 Engine Bridge — Python → Node via JSON over stdin/stdout
// 复用 web/static/s2-vnext/engine.js + voyage.js 的完整逻辑，避免另养一套公式。
// 所有经济/科技/时代/永久科技/航程/存档逻辑以 game_data.json 为唯一源。

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { S2Engine, PythonRandom, validateGameData } from "../web/static/s2-vnext/engine.js";

const GAME_DATA_PATH = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../web/static/s2-vnext/game_data.json");

let _gameData = null;
async function getGameData() {
  if (_gameData) return _gameData;
  const raw = await readFile(GAME_DATA_PATH, "utf8");
  _gameData = validateGameData(JSON.parse(raw));
  return _gameData;
}

function makeEngine(stateSnapshot) {
  // stateSnapshot: { state, rng } as produced by engine.snapshot()
  // If no snapshot, create fresh with seed
  const data = _gameData;
  if (!stateSnapshot) {
    return new S2Engine(data, { seed: 42 });
  }
  // If snapshot is already full {state, rng}, use it
  // If it's just { engine_state: {state, rng} } wrapper, unwrap
  let snap = stateSnapshot;
  if (snap.engine_state) snap = snap.engine_state;
  // snap may be { state, rng } or just state
  if (snap.state && snap.rng) {
    return new S2Engine(data, { state: snap });
  }
  // fallback: try to restore as state only (should not happen)
  const eng = new S2Engine(data, { seed: snap.seed || 42 });
  // attempt to merge fields
  try { eng.restore({ state: snap, rng: snap.rng || new PythonRandom(snap.seed || 42).snapshot() }); } catch {}
  return eng;
}

async function handle(op, payload) {
  const data = await getGameData();
  switch (op) {
    case "init": {
      const seed = payload.seed ?? 42;
      const eng = new S2Engine(data, { seed });
      // apply optional helper/autoDepart settings
      if (typeof payload.helperEnabled === "boolean") eng.setHelperEnabled(payload.helperEnabled);
      if (typeof payload.autoDepart === "boolean") eng.setAutoDepart(payload.autoDepart);
      if (typeof payload.coreHelperEnabled === "boolean") eng.state.coreHelperEnabled = payload.coreHelperEnabled;
      return { ok: true, snapshot: eng.snapshot(), state: eng.state };
    }
    case "snapshot_state": {
      // just validate and return
      const eng = makeEngine(payload.snapshot);
      return { ok: true, snapshot: eng.snapshot(), state: eng.state };
    }
    case "mine": {
      // mine for N minutes, optionally with helper control
      // payload: { snapshot, minutes, withHelper, deterministic }
      const eng = makeEngine(payload.snapshot);
      const minutes = Number(payload.minutes) || 0;
      if (minutes <= 0) return { ok: true, snapshot: eng.snapshot(), state: eng.state, events: [], summary: eng.lastBatchSummary };
      const withHelper = payload.withHelper !== false; // default true
      const deterministic = !!payload.deterministic;
      // 如果 withHelper === false，临时关闭助手，避免模拟期内触发零点采购
      const prevHelper = eng.state.helperEnabled;
      const prevCoreHelper = eng.state.coreHelperEnabled;
      if (!withHelper) {
        eng.setHelperEnabled(false);
        // coreHelper 保持原状还是也关闭？ 药水不应触发核心助手（核心助手是永久科技的笨买，是否算零点？）
        // 按 HANDOFF：药水不能触发或补发大肥鱼现实零点班次采购，但“自动升级、自动购买和后期自动启程照常”
        // 核心助手属于自动购买？还是零点？ 文档说 核心助手默认关闭，可选路线，不是零点。所以保留。
        // 但本地助手（helper）是零点，需要关闭。
      }
      // 对于 resets>=3，mineBlock 会自动走 advanceVoyages 批量
      // 对于 <3，mineBlock 按 settlementMinutes 步进，并处理 autoPurchase/helper
      // 我们直接调 mineBlock
      try {
        eng.mineBlock(minutes, deterministic);
      } catch (e) {
        return { ok: false, error: e.message, snapshot: eng.snapshot() };
      }
      if (!withHelper) {
        // 恢复助手状态，但不补采购
        eng.state.helperEnabled = prevHelper;
        // nextHelperMinute 需要重新同步到当前 minute 之后的下一个 1440 边界，避免立即触发
        // 保持 engine 原有的 nextHelperMinute 逻辑：它在 mineBlock 中已推进，但我们关闭期间未推进
        // 所以需要手动把 nextHelperMinute 设为下一个真实零点模拟值：当前 minute 对应的下一个 1440
        // 但药水不应影响 helper 时钟，所以保持原 helper 时钟不变：回退到原始 nextHelperMinute
        // 简化：恢复原始 nextHelperMinute
        // 重新计算：之前 helper 被关闭后，engine 在 mineBlock 中未更新 nextHelperMinute，所以它仍是旧值
        // 如果旧值已过期（<= current minute），需要推到下一个周期
        // 但药水期间不应采购，所以我们希望 nextHelperMinute 保持不变，若已过期则推到下一个周期
        const curMin = eng.state.minute;
        // 原始 nextHelperMinute 来自 payload.snapshot 的 state.nextHelperMinute
        let origNext = payload.snapshot?.state?.nextHelperMinute ?? eng.state.nextHelperMinute;
        if (curMin >= origNext) {
          // 推到下一个 1440
          const interval = data.rules.helperIntervalMinutes;
          origNext = (Math.floor(curMin / interval) + 1) * interval;
        }
        eng.state.nextHelperMinute = origNext;
        eng.state.helperEnabled = prevHelper;
      }
      return { ok: true, snapshot: eng.snapshot(), state: eng.state, events: eng.lastBlockEvents, summary: eng.lastBatchSummary };
    }
    case "purchase": {
      const eng = makeEngine(payload.snapshot);
      const orders = payload.orders; // [[key, count], ...]
      const automatic = !!payload.automatic;
      const result = eng.upgradeCommand(orders, automatic);
      return { ok: true, snapshot: eng.snapshot(), state: eng.state, result };
    }
    case "purchase_core": {
      const eng = makeEngine(payload.snapshot);
      const key = payload.key;
      const automatic = !!payload.automatic;
      const helper = !!payload.helper;
      const result = eng.purchaseCore(key, { automatic, helper });
      return { ok: true, snapshot: eng.snapshot(), state: eng.state, result };
    }
    case "set_helper": {
      const eng = makeEngine(payload.snapshot);
      const enabled = !!payload.enabled;
      eng.setHelperEnabled(enabled);
      return { ok: true, snapshot: eng.snapshot(), state: eng.state };
    }
    case "helper_purchase": {
      const eng = makeEngine(payload.snapshot);
      const purchases = eng.helperPurchase();
      return { ok: true, snapshot: eng.snapshot(), state: eng.state, purchases };
    }
    case "set_core_helper": {
      const eng = makeEngine(payload.snapshot);
      const enabled = !!payload.enabled;
      const purchases = eng.setCoreHelperEnabled(enabled);
      return { ok: true, snapshot: eng.snapshot(), state: eng.state, purchases };
    }
    case "set_auto_depart": {
      const eng = makeEngine(payload.snapshot);
      eng.setAutoDepart(!!payload.enabled);
      return { ok: true, snapshot: eng.snapshot(), state: eng.state };
    }
    case "depart": {
      const eng = makeEngine(payload.snapshot);
      const result = eng.departPlanet();
      return { ok: true, snapshot: eng.snapshot(), state: eng.state, result };
    }
    case "get_cost": {
      const eng = makeEngine(payload.snapshot);
      const key = payload.key;
      const cost = eng.costFor(key);
      const available = eng.available(key, !!payload.automatic);
      const spec = eng.specs[key];
      return { ok: true, cost, available, spec: spec ? { name: spec.name, maxLevel: spec.maxLevel, era: spec.era } : null, state: eng.state };
    }
    case "shop_entries": {
      const eng = makeEngine(payload.snapshot);
      const entries = [];
      for (const key of eng.localKeys) {
        const spec = eng.specs[key];
        const lv = eng.level(key);
        const max = spec.maxLevel;
        const cost = lv < max ? eng.costFor(key) : 0;
        const era_ok = eng.eraUnlocked(spec.era);
        const avail = eng.available(key);
        const can = avail && eng.state.credits + 1e-9 >= cost && !eng.state.planetComplete;
        let reason = "";
        if (lv >= max) reason = "已满级";
        else if (eng.state.planetComplete) reason = "星球已挖穿，请先【下一个星球】";
        else if (!era_ok) reason = `未解锁时代：${spec.era}`;
        else if (!spec.prerequisites.every(k => eng.level(k) >= 1)) reason = `需前置：${spec.prerequisites.join(",")}`;
        else if (eng.state.credits + 1e-9 < cost) reason = `矿币不足 还差 ${Math.ceil(cost - eng.state.credits)}`;
        else if (can) reason = "可购买";
        entries.push({
          key, name: spec.name, lv, max, cost: Math.ceil(cost), can, reason,
          era: spec.era, region: spec.region, effectKind: spec.effectKind,
          unlocked: era_ok && spec.prerequisites.every(k => eng.level(k)>=1),
          idx: eng.localKeys.indexOf(key)+1
        });
      }
      // 按猫乐园风格，已解锁在前
      const sorted = [...entries].sort((a,b) => (a.unlocked===b.unlocked? a.idx - b.idx : a.unlocked ? -1 : 1));
      return { ok: true, entries: sorted, state: eng.state, snapshot: eng.snapshot() };
    }
    case "status": {
      const eng = makeEngine(payload.snapshot);
      return { ok: true, state: eng.state, snapshot: eng.snapshot(), era: eng.currentEra(), incomeMul: eng.incomeMultiplier(), depthMul: eng.depthMultiplier(), breakdown: eng.multiplierBreakdown() };
    }
    default:
      return { ok: false, error: `unknown op ${op}` };
  }
}

async function main() {
  let input = "";
  process.stdin.setEncoding("utf8");
  for await (const chunk of process.stdin) input += chunk;
  input = input.trim();
  if (!input) {
    console.error(JSON.stringify({ ok: false, error: "empty input" }));
    process.exit(1);
  }
  let req;
  try { req = JSON.parse(input); } catch (e) { console.error(JSON.stringify({ ok: false, error: "invalid json: " + e.message })); process.exit(1); }
  try {
    const res = await handle(req.op, req.payload || {});
    process.stdout.write(JSON.stringify(res));
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, error: e.message, stack: e.stack }));
    process.exit(0);
  }
}

main();
