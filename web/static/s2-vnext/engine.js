const UINT32_RANGE = 4294967296;
const TWO_PI = Math.PI * 2;
const IMPLEMENTED_EFFECT_KINDS = new Set([
  "speed_compound", "parallel", "cats", "sharpness", "income", "fragility",
  "extra_depth", "coordination", "crit_chance", "crit_damage", "shift_relay",
  "momentum", "teamwork", "penetration", "resonance", "pressure", "network",
  "heat", "diversity", "cascade", "precision", "compression", "lens",
]);

export function validateGameData(data) {
  if (!data || data.schemaVersion !== 3) throw new Error(`Unsupported S2 schema: ${data?.schemaVersion}`);
  const required = ["settlementMinutes", "baseCreditsPerMinute", "baseDepthPerMinute", "manualAutomationThreshold", "autoPurchaseIntervalMinutes", "autoPurchaseBudget", "autoReserveManualLevels", "randomAlgorithm", "randomSigma", "dailyUpgradeAuditMin", "dailyUpgradeAuditMax", "developmentTargetDepth", "helperIntervalMinutes", "baseCriticalDamage", "manualBurstWarningLevels", "batchCommandMaxLevels"];
  required.forEach((key) => { if (!(key in data.rules)) throw new Error(`Missing rule: ${key}`); });
  if (data.rules.randomAlgorithm !== "python-mt19937-v1") throw new Error("Unsupported random algorithm");
  if (!(Number(data.strategy?.opportunityCheckIntervalMinutes) > 0)) throw new Error("Missing opportunity check interval");
  if (data.resources.length !== 1 || data.resources[0].key !== "credits") throw new Error("v3 requires credits as the only resource");
  if (data.rules.helperIntervalMinutes !== 1440) throw new Error("Helper must use the daily clock");
  if (!Number.isInteger(data.rules.batchCommandMaxLevels) || data.rules.batchCommandMaxLevels <= 0) throw new Error("Invalid batch size");
  const eras = new Set(data.eras.map((item) => item.key));
  const regions = new Set(data.multiplierRegions.map((item) => item.key));
  const keys = new Set();
  data.upgrades.forEach((item) => {
    if (keys.has(item.key)) throw new Error(`Duplicate upgrade ${item.key}`);
    keys.add(item.key);
    if (!eras.has(item.era) || !regions.has(item.region)) throw new Error(`Invalid era/region for ${item.key}`);
    if (item.manualTarget !== data.rules.manualAutomationThreshold) throw new Error(`Invalid manual target for ${item.key}`);
    if (item.status === "active" && !IMPLEMENTED_EFFECT_KINDS.has(item.effectKind)) {
      throw new Error(`Unsupported active effect ${item.effectKind} for ${item.key}`);
    }
  });
  data.upgrades.forEach((item) => item.prerequisites.forEach((key) => {
    if (!keys.has(key)) throw new Error(`Unknown prerequisite ${key}`);
  }));
  return data;
}

export async function loadGameData(url = "./game_data.json") {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`Unable to load S2 game data: ${response.status}`);
  return validateGameData(await response.json());
}

export class PythonRandom {
  constructor(seed = 42, snapshot = null) {
    this.mt = new Uint32Array(624);
    this.index = 624;
    this.gaussNext = null;
    if (snapshot) this.restore(snapshot); else this.seed(seed);
  }
  seed(seedValue) {
    let value;
    try { value = BigInt(seedValue); } catch { value = 42n; }
    if (value < 0n) value = -value;
    const key = [];
    do { key.push(Number(value & 0xffffffffn)); value >>= 32n; } while (value > 0n);
    this.initByArray(key);
    this.gaussNext = null;
  }
  initGenRand(seed) {
    this.mt[0] = seed >>> 0;
    for (let index = 1; index < 624; index += 1) {
      const previous = this.mt[index - 1];
      this.mt[index] = (Math.imul(1812433253, previous ^ (previous >>> 30)) + index) >>> 0;
    }
    this.index = 624;
  }
  initByArray(key) {
    this.initGenRand(19650218);
    let i = 1; let j = 0; let count = Math.max(624, key.length);
    for (; count > 0; count -= 1) {
      const previous = this.mt[i - 1];
      this.mt[i] = ((this.mt[i] ^ Math.imul(previous ^ (previous >>> 30), 1664525)) + key[j] + j) >>> 0;
      i += 1; j += 1;
      if (i >= 624) { this.mt[0] = this.mt[623]; i = 1; }
      if (j >= key.length) j = 0;
    }
    for (count = 623; count > 0; count -= 1) {
      const previous = this.mt[i - 1];
      this.mt[i] = ((this.mt[i] ^ Math.imul(previous ^ (previous >>> 30), 1566083941)) - i) >>> 0;
      i += 1;
      if (i >= 624) { this.mt[0] = this.mt[623]; i = 1; }
    }
    this.mt[0] = 0x80000000;
    this.index = 624;
  }
  nextUint32() {
    if (this.index >= 624) {
      for (let index = 0; index < 624; index += 1) {
        const y = (this.mt[index] & 0x80000000) | (this.mt[(index + 1) % 624] & 0x7fffffff);
        let value = this.mt[(index + 397) % 624] ^ (y >>> 1);
        if (y & 1) value ^= 0x9908b0df;
        this.mt[index] = value >>> 0;
      }
      this.index = 0;
    }
    let y = this.mt[this.index]; this.index += 1;
    y ^= y >>> 11; y ^= (y << 7) & 0x9d2c5680; y ^= (y << 15) & 0xefc60000; y ^= y >>> 18;
    return y >>> 0;
  }
  random() {
    const a = this.nextUint32() >>> 5; const b = this.nextUint32() >>> 6;
    return (a * 67108864 + b) / 9007199254740992;
  }
  gauss(mu = 0, sigma = 1) {
    let value = this.gaussNext; this.gaussNext = null;
    if (value === null) {
      const angle = this.random() * TWO_PI;
      const radius = Math.sqrt(-2 * Math.log(1 - this.random()));
      value = Math.cos(angle) * radius;
      this.gaussNext = Math.sin(angle) * radius;
    }
    return mu + value * sigma;
  }
  snapshot() { return { mt: Array.from(this.mt), index: this.index, gaussNext: this.gaussNext }; }
  restore(snapshot) {
    if (!snapshot || !Array.isArray(snapshot.mt) || snapshot.mt.length !== 624
      || snapshot.mt.some((value) => !Number.isInteger(value) || value < 0 || value >= UINT32_RANGE)
      || !Number.isInteger(snapshot.index) || snapshot.index < 0 || snapshot.index > 624
      || (snapshot.gaussNext !== null && !Number.isFinite(snapshot.gaussNext))) throw new Error("Invalid RNG snapshot");
    this.mt.set(snapshot.mt.map((value) => value >>> 0));
    this.index = Number(snapshot.index); this.gaussNext = snapshot.gaussNext ?? null;
  }
}

function objectOf(keys, value = 0) { return Object.fromEntries(keys.map((key) => [key, value])); }
function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }

export class S2Engine {
  constructor(data, options = {}) {
    this.data = validateGameData(data);
    this.rules = data.rules;
    this.eras = data.eras;
    this.eraByKey = Object.fromEntries(data.eras.map((item) => [item.key, item]));
    this.eraSequence = data.eras.map((item) => item.key);
    this.specs = Object.fromEntries(data.upgrades.map((item) => [item.key, item]));
    this.localKeys = data.upgrades.map((item) => item.key);
    this.priority = data.strategy.priority.filter((key) => this.specs[key]);
    this.rng = new PythonRandom(options.seed ?? 42);
    this.state = this.newState(options.seed ?? 42);
    this.lastBlockEvents = [];
    if (options.state) this.restore(options.state);
  }

  newState(seed = 42) {
    return {
      schemaVersion: this.data.schemaVersion, gameVersion: this.data.gameVersion,
      contentVersion: this.data.contentVersion, seed: Number(seed),
      day: 1, minute: 0, depth: 0, credits: 0,
      targetDepth: Number(this.rules.developmentTargetDepth),
      levels: objectOf(this.localKeys), manualLevels: objectOf(this.localKeys),
      autoUnlocked: [], everKeys: [], dailyManualLevels: 0, maxDailyManualLevels: 0,
      totalManualLevels: 0, totalAutoLevels: 0, eraFirstDays: {}, autoCursor: 0,
      nextAutoMinute: Number(this.rules.autoPurchaseIntervalMinutes),
      helperEnabled: true, nextHelperMinute: Number(this.rules.helperIntervalMinutes),
      totalHelperLevels: 0, dailyHelperLevels: 0, totalManualCommands: 0,
      lastHelperReport: null,
    };
  }

  snapshot() { return { state: structuredClone(this.state), rng: this.rng.snapshot() }; }
  restore(payload) {
    const saved = structuredClone(payload);
    if (!saved || saved.state?.schemaVersion !== 3 || saved.state.gameVersion !== this.data.gameVersion) throw new Error("旧版存档与助手版不兼容");
    const state = saved.state;
    const counters = ["day", "minute", "dailyManualLevels", "maxDailyManualLevels", "totalManualLevels",
      "totalAutoLevels", "autoCursor", "totalHelperLevels", "dailyHelperLevels", "totalManualCommands"];
    const invalid = () => { throw new Error("存档字段损坏"); };
    if (counters.some((key) => !Number.isSafeInteger(state[key]) || state[key] < 0)
      || !Number.isSafeInteger(state.seed)
      || ["depth", "credits", "targetDepth"].some((key) => !Number.isFinite(state[key]) || state[key] < 0)
      || state.minute % this.rules.settlementMinutes || state.day !== Math.floor(state.minute / 1440) + 1
      || typeof state.helperEnabled !== "boolean" || !state.eraFirstDays || typeof state.eraFirstDays !== "object") invalid();
    for (const [key, interval] of [["nextAutoMinute", this.rules.autoPurchaseIntervalMinutes], ["nextHelperMinute", this.rules.helperIntervalMinutes]]) {
      if (!Number.isSafeInteger(state[key]) || state[key] !== (Math.floor(state.minute / interval) + 1) * interval) invalid();
    }
    if (!state.levels || typeof state.levels !== "object"
      || !state.manualLevels || typeof state.manualLevels !== "object") invalid();
    const isFirstTenDaySave = !Object.hasOwn(state, "contentVersion");
    for (const key of this.localKeys) {
      const hasLevel = Object.hasOwn(state.levels, key);
      const hasManualLevel = Object.hasOwn(state.manualLevels, key);
      if (hasLevel !== hasManualLevel) invalid();
      if (!hasLevel) {
        if (!isFirstTenDaySave || this.specs[key].addedIn !== "thirty-day") invalid();
        state.levels[key] = 0;
        state.manualLevels[key] = 0;
      }
      if (!Number.isInteger(state.levels[key]) || state.levels[key] < 0
        || state.levels[key] > this.specs[key].maxLevel
        || !Number.isInteger(state.manualLevels[key]) || state.manualLevels[key] < 0
        || state.manualLevels[key] > this.specs[key].manualTarget) invalid();
    }
    for (const field of ["autoUnlocked", "everKeys"]) {
      if (!Array.isArray(state[field]) || state[field].some((key) => !Object.hasOwn(this.specs, key))
        || new Set(state[field]).size !== state[field].length) invalid();
    }
    if (this.localKeys.some((key) => state.manualLevels[key] > state.levels[key]
      || state.autoUnlocked.includes(key) !== (state.manualLevels[key] === this.specs[key].manualTarget))) invalid();
    const report = state.lastHelperReport;
    if (report !== null && (!report || !Array.isArray(report.items)
      || !Number.isInteger(report.minute) || report.minute < 0 || report.minute > state.minute
      || report.levels !== report.items.length || !Number.isFinite(report.spent) || report.spent < 0
      || report.items.some((item) => !item || !Object.hasOwn(this.specs, item.key)
        || !Number.isInteger(item.level) || item.level <= 0 || !Number.isFinite(item.cost) || item.cost < 0))) invalid();
    state.contentVersion = this.data.contentVersion;
    this.rng.restore(saved.rng);
    this.state = state;
  }
  level(key) { return Number(this.state.levels[key] || 0); }
  costFor(key, level = this.level(key)) {
    const spec = this.specs[key]; return Number(spec.baseCost) * Number(spec.costGrowth) ** level;
  }
  eraAutomationCount(era) {
    return this.state.autoUnlocked.filter((key) => this.specs[key].era === era).length;
  }
  eraUnlocked(era) {
    if (era === this.eraSequence[0]) return true;
    const definition = this.eraByKey[era];
    const previous = this.eraSequence[this.eraSequence.indexOf(era) - 1];
    return this.state.depth >= Number(definition.unlockDepth) && this.eraAutomationCount(previous) >= Number(definition.previousEraAutomations);
  }
  currentEra() {
    return [...this.eraSequence].reverse().find((era) => this.eraUnlocked(era)) || this.eraSequence[0];
  }
  available(key, automatic = false) {
    const spec = this.specs[key];
    if (!spec || this.level(key) >= spec.maxLevel || spec.status !== "active") return false;
    if (automatic && !this.state.autoUnlocked.includes(key)) return false;
    if (!automatic && this.state.manualLevels[key] >= spec.manualTarget) return false;
    return this.eraUnlocked(spec.era) && this.state.depth >= Number(spec.unlockDepth)
      && spec.prerequisites.every((required) => this.level(required) >= 1);
  }
  manualCandidates() { return this.localKeys.filter((key) => this.available(key)); }
  reserveCost() {
    const costs = [];
    this.manualCandidates().forEach((key) => {
      const spec = this.specs[key];
      const remaining = spec.manualTarget - this.state.manualLevels[key];
      for (let offset = 0; offset < remaining; offset += 1) costs.push(this.costFor(key, this.level(key) + offset));
    });
    costs.sort((a, b) => a - b);
    const count = Number(this.rules.autoReserveManualLevels);
    if (!costs.length) return 0;
    while (costs.length < count) costs.push(costs[costs.length - 1]);
    return costs.slice(0, count).reduce((sum, value) => sum + value, 0);
  }
  purchase(key, automatic = false, helper = false) {
    if (automatic && helper) return { ok: false, reason: "source" };
    if (!this.available(key, automatic)) return { ok: false, reason: "locked" };
    const cost = this.costFor(key);
    if (this.state.credits + 1e-9 < cost) return { ok: false, reason: "credits" };
    if (automatic && this.state.credits - cost + 1e-9 < this.reserveCost()) return { ok: false, reason: "reserve" };
    this.state.credits = Math.max(0, this.state.credits - cost); this.state.levels[key] += 1;
    if (!this.state.everKeys.includes(key)) this.state.everKeys.push(key);
    if (automatic) this.state.totalAutoLevels += 1;
    else {
      // Legacy field: commissioning levels, shared by the player and helper.
      this.state.manualLevels[key] += 1;
      if (helper) {
        this.state.dailyHelperLevels += 1; this.state.totalHelperLevels += 1;
      } else {
        this.state.dailyManualLevels += 1; this.state.totalManualLevels += 1;
        this.state.maxDailyManualLevels = Math.max(this.state.maxDailyManualLevels, this.state.dailyManualLevels);
      }
      if (this.state.manualLevels[key] === this.specs[key].manualTarget) {
        if (!this.state.autoUnlocked.includes(key)) this.state.autoUnlocked.push(key);
        if (!(this.specs[key].era in this.state.eraFirstDays)) this.state.eraFirstDays[this.specs[key].era] = this.state.day;
      }
    }
    return { ok: true, key, cost, level: this.level(key), automatic, source: automatic ? "auto" : helper ? "helper" : "manual" };
  }
  upgradeCommand(orders, automatic = false) {
    if (!Array.isArray(orders) || !orders.length || orders.some((order) =>
      !Array.isArray(order) || order.length !== 2 || typeof order[0] !== "string" || !Object.hasOwn(this.specs, order[0])
      || !Number.isInteger(order[1]) || order[1] <= 0)
      || orders.reduce((sum, [, count]) => sum + count, 0) > this.rules.batchCommandMaxLevels) {
      return { ok: false, reason: "invalid", purchases: [] };
    }
    const purchases = []; let reason = "";
    outer: for (const [key, count] of orders) {
      for (let i = 0; i < count; i += 1) {
        const result = this.purchase(key, automatic);
        if (!result.ok) { reason = result.reason; break outer; }
        purchases.push(result);
      }
    }
    if (purchases.length && !automatic) this.state.totalManualCommands += 1;
    return { ...purchases.at(-1), ok: purchases.length > 0, reason, purchases };
  }
  setHelperEnabled(enabled) {
    if (typeof enabled !== "boolean") throw new Error("Helper setting must be boolean");
    this.state.helperEnabled = enabled;
  }
  helperPurchase() {
    const purchases = [];
    for (let key = this.state.helperEnabled ? this.chooseUpgrade("cheapest") : null; key; key = this.chooseUpgrade("cheapest")) {
      const result = this.purchase(key, false, true);
      if (!result.ok) break;
      purchases.push(result);
    }
    this.state.lastHelperReport = {
      minute: this.state.minute, levels: purchases.length,
      spent: purchases.reduce((sum, item) => sum + item.cost, 0),
      items: purchases.map(({ key, level, cost }) => ({ key, level, cost })),
    };
    return purchases;
  }
  effectLevels() {
    const totals = {};
    this.localKeys.forEach((key) => {
      const level = this.level(key); if (!level) return;
      const kind = this.specs[key].effectKind;
      totals[kind] = (totals[kind] || 0) + Number(this.specs[key].effectPerLevel) * level;
    });
    return totals;
  }
  multiplierBreakdown() {
    const e = this.effectLevels();
    let speed = 1;
    this.localKeys.forEach((key) => {
      const level = this.level(key); const spec = this.specs[key];
      if (level && spec.effectKind === "speed_compound") speed *= (1 + Number(spec.effectPerLevel)) ** level;
    });
    const parallel = 1 + (e.parallel || 0); const cats = 1 + (e.cats || 0);
    const sharpness = 1 + (e.sharpness || 0); const fragility = 1 + (e.fragility || 0);
    const income = 1 + (e.income || 0); const extraDepth = 1 + (e.extra_depth || 0);
    const critChance = Math.min(0.65, e.crit_chance || 0); const critDamage = Number(this.rules.baseCriticalDamage) + (e.crit_damage || 0);
    const critical = 1 + critChance * critDamage;
    const catLevels = this.localKeys.reduce((sum, key) => sum + (this.specs[key].effectKind === "cats" ? this.level(key) : 0), 0);
    const coordination = 1 + (e.coordination || 0) * catLevels;
    const teamwork = 1 + (e.teamwork || 0) * Math.sqrt(Math.max(0, this.state.minute / 1440));
    const momentum = 1 + (e.momentum || 0) * Math.min(1, (this.state.minute % 1440) / 240);
    const autoCount = this.state.autoUnlocked.length;
    const resonance = 1 + (e.resonance || 0) * autoCount;
    const shiftRelay = 1 + (e.shift_relay || 0) * autoCount;
    const penetration = 1 + (e.penetration || 0) * Math.max(0, critical - 1);
    const pressure = 1 + (e.pressure || 0) * Math.log10(1 + this.state.depth) / 10;
    const activeRegions = new Set(this.localKeys.filter((key) => this.level(key)).map((key) => this.specs[key].region)).size;
    const diversity = 1 + (e.diversity || 0) * activeRegions;
    const network = 1 + (e.network || 0) * Math.sqrt(parallel * cats);
    const heat = 1 + (e.heat || 0) * (momentum + Math.log10(speed));
    const cascade = this.eraSequence.reduce((product, era) => {
      const activeSpecs = this.localKeys.filter((key) => this.specs[key].era === era && this.specs[key].status === "active");
      if (!activeSpecs.length) return product;
      const automated = activeSpecs.filter((key) => this.state.autoUnlocked.includes(key)).length;
      return product * (1 + (e.cascade || 0) * automated / activeSpecs.length);
    }, 1);
    const precision = 1 + (e.precision || 0) * fragility * critical
      * (1 + Math.max(0, (e.crit_chance || 0) - 0.65));
    const compression = 1 + (e.compression || 0) * Math.sqrt(penetration * pressure);
    const lens = 1 + (e.lens || 0) * Math.log10(1 + this.state.depth) / 10 * compression;
    return {
      speed, parallel, cats, sharpness, fragility, income, extra_depth: extraDepth,
      critical, coordination, teamwork, momentum, resonance, shift_relay: shiftRelay,
      penetration, pressure, diversity, network, heat, cascade, precision, compression, lens,
    };
  }
  incomeMultiplier() {
    const f = this.multiplierBreakdown();
    return ["speed", "parallel", "cats", "sharpness", "fragility", "critical", "coordination", "teamwork", "momentum", "resonance", "income", "shift_relay", "diversity", "network", "heat", "cascade", "precision"].reduce((product, key) => product * f[key], 1);
  }
  depthMultiplier() {
    const f = this.multiplierBreakdown();
    return ["speed", "parallel", "cats", "sharpness", "fragility", "critical", "coordination", "teamwork", "momentum", "resonance", "extra_depth", "penetration", "pressure", "network", "cascade", "precision", "compression", "lens"].reduce((product, key) => product * f[key], 1);
  }
  autoPurchase() {
    const active = [...this.state.autoUnlocked].sort(); if (!active.length) return [];
    const budget = Math.min(Number(this.rules.autoPurchaseBudget), active.length);
    const start = this.state.autoCursor % active.length;
    const ordered = active.slice(start).concat(active.slice(0, start));
    this.state.autoCursor = (start + budget) % active.length;
    const bought = [];
    for (const key of ordered) {
      if (bought.length >= budget) break;
      const result = this.purchase(key, true); if (result.ok) bought.push(result);
    }
    return bought;
  }
  mineBlock(minutes = Number(this.rules.settlementMinutes), deterministic = false) {
    const step = Number(this.rules.settlementMinutes);
    if (!Number.isFinite(minutes) || minutes <= 0 || minutes % step) throw new Error("mineBlock must use settlement-sized minutes");
    const bought = [];
    this.lastBlockEvents = [];
    for (let elapsed = 0; elapsed < minutes; elapsed += step) {
      const noise = deterministic ? 1 : clamp(this.rng.gauss(1, Number(this.rules.randomSigma)), 0.85, 1.15);
      this.state.credits += Number(this.rules.baseCreditsPerMinute) * this.incomeMultiplier() * step * noise;
      this.state.depth += Number(this.rules.baseDepthPerMinute) * this.depthMultiplier() * step * noise;
      this.state.minute += step;
      this.startNewDay();
      while (this.state.minute >= this.state.nextAutoMinute) {
        const purchases = this.autoPurchase();
        bought.push(...purchases);
        this.lastBlockEvents.push(...purchases.map((item) => ({ ...item, minute: this.state.minute })));
        this.state.nextAutoMinute += Number(this.rules.autoPurchaseIntervalMinutes);
      }
      while (this.state.minute >= this.state.nextHelperMinute) {
        this.lastBlockEvents.push(...this.helperPurchase().map((item) => ({ ...item, minute: this.state.minute })));
        this.state.nextHelperMinute += Number(this.rules.helperIntervalMinutes);
      }
    }
    return bought;
  }
  startNewDay() {
    const day = Math.floor(this.state.minute / 1440) + 1;
    if (day !== this.state.day) {
      this.state.day = day; this.state.dailyManualLevels = 0; this.state.dailyHelperLevels = 0;
    }
  }
  chooseUpgrade(route = "balanced") {
    let affordable = this.manualCandidates().filter((key) => this.costFor(key) <= this.state.credits + 1e-9);
    if (!affordable.length) return null;
    const priority = Object.fromEntries(this.priority.map((key, index) => [key, index]));
    if (route === "cheapest") return affordable.sort((a, b) => this.costFor(a) - this.costFor(b) || (priority[a] ?? 999) - (priority[b] ?? 999))[0];
    if (route === "depth" || route === "income") {
      const depthKinds = new Set(["speed_compound", "parallel", "cats", "sharpness", "fragility", "crit_chance", "crit_damage", "coordination", "teamwork", "momentum", "resonance", "extra_depth", "penetration", "pressure", "network", "cascade", "precision", "compression", "lens"]);
      const incomeKinds = new Set([...depthKinds].filter((key) => !["extra_depth", "penetration", "pressure", "compression", "lens"].includes(key)).concat(["income", "shift_relay", "diversity", "heat"]));
      const preferred = route === "depth" ? depthKinds : incomeKinds;
      const matching = affordable.filter((key) => preferred.has(this.specs[key].effectKind));
      if (matching.length) affordable = matching;
    }
    const started = affordable.filter((key) => this.state.manualLevels[key] > 0);
    const pool = started.length ? started : affordable;
    return pool.sort((a, b) => (priority[a] ?? 999) - (priority[b] ?? 999) || this.costFor(a) - this.costFor(b))[0];
  }
  strategyStep(route = "balanced") {
    const key = this.chooseUpgrade(route); if (!key) return null;
    const result = this.upgradeCommand([[key, 1]]); return result.ok ? result : null;
  }
  strategyVisit(route = "balanced") {
    const purchases = [];
    for (let item = this.strategyStep(route); item; item = this.strategyStep(route)) purchases.push(item);
    return purchases;
  }
}

export function runReplay(data, options = {}) {
  const days = options.days ?? 10; const seed = options.seed ?? 42;
  const profileKey = options.profile ?? "daily"; const route = options.route ?? "balanced";
  const profile = profileKey === "opportunity"
    ? { checkMinutes: Array.from({ length: 1440 / Number(data.strategy.opportunityCheckIntervalMinutes) }, (_, index) => (index + 1) * Number(data.strategy.opportunityCheckIntervalMinutes)) }
    : data.strategy.profiles[profileKey];
  if (!profile) throw new Error(`Unknown profile ${profileKey}`);
  const checks = new Set(profile.checkMinutes.map(Number));
  const engine = new S2Engine(data, { seed }); const snapshots = []; const events = [];
  for (let day = 1; day <= days; day += 1) {
    if (day > 1) engine.startNewDay();
    const autoBefore = engine.state.totalAutoLevels;
    const manualBefore = engine.state.totalManualLevels; const helperBefore = engine.state.totalHelperLevels;
    const commandsBefore = engine.state.totalManualCommands; let visits = 0;
    for (let minute = Number(data.rules.settlementMinutes); minute <= 1440; minute += Number(data.rules.settlementMinutes)) {
      engine.mineBlock();
      engine.lastBlockEvents.forEach((item) => events.push({ day, minute, source: item.source, key: item.key, level: item.level, cost: item.cost }));
      if (checks.has(minute)) {
        visits += 1;
        engine.strategyVisit(route).forEach((item) => events.push({ day, minute, source: "manual", key: item.key, level: item.level, cost: item.cost }));
      }
    }
    snapshots.push({
      day, depth: engine.state.depth, credits: engine.state.credits,
      manualLevels: engine.state.totalManualLevels - manualBefore,
      helperLevels: engine.state.totalHelperLevels - helperBefore,
      manualCommands: engine.state.totalManualCommands - commandsBefore, visits,
      autoLevels: engine.state.totalAutoLevels - autoBefore,
      autoTechnologies: engine.state.autoUnlocked.length,
      nodesReached: engine.state.everKeys.length,
      currentEra: engine.currentEra(), incomeMultiplier: engine.incomeMultiplier(),
      depthMultiplier: engine.depthMultiplier(), multipliers: engine.multiplierBreakdown(),
    });
  }
  return { engine, snapshots, events };
}
