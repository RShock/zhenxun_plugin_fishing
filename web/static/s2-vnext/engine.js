import { compileVoyage, sampleVoyage, earnedCores } from "./voyage.js?v=3-prestige-3";

const UINT32_RANGE = 4294967296;
const TWO_PI = Math.PI * 2;
const IMPLEMENTED_EFFECT_KINDS = new Set([
  "speed_compound", "parallel", "cats", "sharpness", "income", "fragility",
  "extra_depth", "coordination", "crit_chance", "crit_damage", "shift_relay",
  "momentum", "teamwork", "penetration", "resonance",
]);

export function validateGameData(data) {
  if (!data || data.schemaVersion !== 3) throw new Error(`Unsupported S2 schema: ${data?.schemaVersion}`);
  const required = ["settlementMinutes", "baseCreditsPerMinute", "baseDepthPerMinute", "manualAutomationThreshold", "autoPurchaseIntervalMinutes", "autoPurchaseBudget", "autoReserveManualLevels", "randomAlgorithm", "randomSigma", "dailyUpgradeAuditMin", "dailyUpgradeAuditMax", "developmentTargetDepth", "helperIntervalMinutes", "baseCriticalDamage", "manualBurstWarningLevels", "batchCommandMaxLevels"];
  required.forEach((key) => { if (!(key in data.rules)) throw new Error(`Missing rule: ${key}`); });
  if (data.rules.randomAlgorithm !== "python-mt19937-v1") throw new Error("Unsupported random algorithm");
  if (!(Number(data.strategy?.opportunityCheckIntervalMinutes) > 0)) throw new Error("Missing opportunity check interval");
  const resources = data.prestige ? ["credits", "cores"] : ["credits"];
  if (JSON.stringify(data.resources.map((item) => item.key)) !== JSON.stringify(resources)) throw new Error("Invalid resource contract");
  if (data.contentVersion?.startsWith("prestige-") && !data.prestige) throw new Error("Missing prestige rules");
  if (data.prestige) {
    const p = data.prestige;
    if (!Number.isFinite(p.planetTargetDepth) || p.planetTargetDepth <= 0
      || (["prestige-2", "prestige-3"].includes(data.contentVersion) && (!Number.isSafeInteger(p.galaxyTargetPlanets)
        || p.galaxyTargetPlanets < 1 || !Number.isSafeInteger(earnedCores(p.galaxyTargetPlanets, p.rewardStep))))
      || !Number.isInteger(p.rewardStep) || p.rewardStep < 1
      || !Number.isInteger(p.historyLimit) || p.historyLimit < 1
      || !Array.isArray(p.upgrades) || !p.upgrades.length) throw new Error("Invalid prestige rules");
    if (data.contentVersion === "prestige-3" && (p.openingBurstSeconds !== 1 || !p.legacyCorePrices)) throw new Error("Missing interstellar rules");
    const kinds = new Set(["speed_strength", "income_strength", "depth_strength", "equipment_strength", "line_synergy", "global_speed", "global_linear", "local_discount", "completion_depth", "opening_burst"]);
    const keys = new Set();
    for (const spec of p.upgrades) {
      if (typeof spec.key !== "string" || keys.has(spec.key) || !kinds.has(spec.effectKind)
        || !Number.isInteger(spec.unlockResets) || spec.unlockResets < 1
        || !Number.isInteger(spec.maxLevel) || spec.maxLevel < 1 || spec.maxLevel > 20
        || !Number.isSafeInteger(spec.baseCost) || spec.baseCost < 1
        || !Number.isSafeInteger(spec.costGrowth) || spec.costGrowth < 1
        || !Number.isFinite(spec.effectPerLevel) || spec.effectPerLevel <= 0
        || !Number.isSafeInteger(spec.baseCost * spec.costGrowth ** (spec.maxLevel - 1))) throw new Error("Invalid core technology");
      keys.add(spec.key);
    }
  }
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
    this.coreSpecs = Object.fromEntries((data.prestige?.upgrades || []).map((item) => [item.key, item]));
    this.rng = new PythonRandom(options.seed ?? 42);
    this.state = this.newState(options.seed ?? 42);
    this.lastBlockEvents = [];
    this.lastBatchSummary = { planets: 0, compiled: 0, events: 0 };
    if (options.state) this.restore(options.state);
  }

  newState(seed = 42) {
    return {
      schemaVersion: this.data.schemaVersion, gameVersion: this.data.gameVersion,
      contentVersion: this.data.contentVersion, seed: Number(seed),
      day: 1, minute: 0, depth: 0, credits: 0,
      targetDepth: Number(this.data.prestige?.planetTargetDepth ?? this.rules.developmentTargetDepth),
      levels: objectOf(this.localKeys), manualLevels: objectOf(this.localKeys),
      autoUnlocked: [], everKeys: [], dailyManualLevels: 0, maxDailyManualLevels: 0,
      totalManualLevels: 0, totalAutoLevels: 0, eraFirstDays: {}, autoCursor: 0,
      nextAutoMinute: Number(this.rules.autoPurchaseIntervalMinutes),
      helperEnabled: true, nextHelperMinute: Number(this.rules.helperIntervalMinutes),
      totalHelperLevels: 0, dailyHelperLevels: 0, totalManualCommands: 0,
      lastHelperReport: null,
      resets: 0, completedPlanets: 0, cores: 0, coreLevels: objectOf(Object.keys(this.coreSpecs)),
      planetComplete: false, planetStartedMinute: 0, allMaxedMinute: null,
      autoDepart: true, planetHistory: [], coreAutoRoute: "off",
      legacyCoreLevels: objectOf(Object.keys(this.coreSpecs)),
    };
  }

  snapshot() { return { state: structuredClone(this.state), rng: this.rng.snapshot() }; }
  restore(payload) {
    const saved = structuredClone(payload);
    if (!saved || saved.state?.schemaVersion !== 3 || saved.state.gameVersion !== this.data.gameVersion) throw new Error("旧版存档与助手版不兼容");
    const state = saved.state;
    const prestigeFields = ["resets", "completedPlanets", "cores", "coreLevels", "planetComplete",
      "planetStartedMinute", "allMaxedMinute", "autoDepart", "planetHistory"];
    const legacy = !state.contentVersion || state.contentVersion === "thirty-day-eras-1";
    if (legacy && prestigeFields.every((key) => !Object.hasOwn(state, key))) {
      const defaults = this.newState(state.seed);
      for (const key of prestigeFields) state[key] = defaults[key];
      state.targetDepth = defaults.targetDepth;
    } else if (prestigeFields.some((key) => !Object.hasOwn(state, key))) throw new Error("转生存档字段损坏");
    else if (!legacy && state.contentVersion && !["prestige-1", "prestige-2", this.data.contentVersion].includes(state.contentVersion)) throw new Error("不支持此内容版本");
    if (state.contentVersion !== this.data.contentVersion) {
      state.coreAutoRoute = "off";
      if (!legacy && state.coreLevels && !Object.hasOwn(state.coreLevels, "planet_drive")
        && state.contentVersion === "prestige-1" && this.coreSpecs.planet_drive) state.coreLevels.planet_drive = 0;
      state.legacyCoreLevels = objectOf(Object.keys(this.coreSpecs));
      if (!legacy && state.coreLevels) {
        for (const key of Object.keys(this.data.prestige.legacyCorePrices)) {
          if (!Object.hasOwn(state.coreLevels, key)) throw new Error("旧版永久科技字段损坏");
          state.legacyCoreLevels[key] = state.coreLevels[key];
        }
        for (const key of Object.keys(this.coreSpecs)) {
          if (!Object.hasOwn(this.data.prestige.legacyCorePrices, key)) {
            if (Object.hasOwn(state.coreLevels, key) && state.coreLevels[key] !== 0) throw new Error("旧版含未发布科技");
            state.coreLevels[key] = 0;
          }
        }
      }
    }
    if (legacy && state.resets === 0 && state.completedPlanets === 0) {
      state.targetDepth = this.newState(state.seed).targetDepth;
      if (state.coreLevels && Object.keys(state.coreLevels).length === 0) state.coreLevels = objectOf(Object.keys(this.coreSpecs));
    }
    const counters = ["day", "dailyManualLevels", "maxDailyManualLevels", "totalManualLevels",
      "totalAutoLevels", "autoCursor", "totalHelperLevels", "dailyHelperLevels", "totalManualCommands"];
    const invalid = () => { throw new Error("存档字段损坏"); };
    if (counters.some((key) => !Number.isSafeInteger(state[key]) || state[key] < 0)
      || !Number.isSafeInteger(state.seed)
      || ["depth", "credits", "targetDepth"].some((key) => !Number.isFinite(state[key]) || state[key] < 0)
      || !Number.isFinite(state.minute) || state.minute < 0 || state.minute > Number.MAX_SAFE_INTEGER
      || (state.resets < 3 && state.minute % this.rules.settlementMinutes)
      || state.day !== Math.floor(state.minute / 1440) + 1
      || typeof state.helperEnabled !== "boolean" || !state.eraFirstDays || typeof state.eraFirstDays !== "object") invalid();
    if (["resets", "completedPlanets", "cores"].some((key) => !Number.isSafeInteger(state[key]) || state[key] < 0)
      || typeof state.planetComplete !== "boolean" || typeof state.autoDepart !== "boolean"
      || !["off", "balanced", "speed", "rebuild", "burst"].includes(state.coreAutoRoute)
      || state.completedPlanets > (this.data.prestige?.galaxyTargetPlanets ?? 1000000)
      || state.completedPlanets !== state.resets + Number(state.planetComplete)
      || !Number.isFinite(state.planetStartedMinute) || state.planetStartedMinute < 0
      || state.planetStartedMinute > state.minute
      || state.targetDepth !== Number(this.data.prestige?.planetTargetDepth ?? this.rules.developmentTargetDepth)
      || (state.planetComplete && state.depth !== state.targetDepth)
      || (state.allMaxedMinute !== null && (!Number.isFinite(state.allMaxedMinute)
        || state.allMaxedMinute < state.planetStartedMinute || state.allMaxedMinute > state.minute))
      || !state.coreLevels || typeof state.coreLevels !== "object" || Array.isArray(state.coreLevels)
      || Object.keys(state.coreLevels).length !== Object.keys(this.coreSpecs).length
      || !state.legacyCoreLevels || typeof state.legacyCoreLevels !== "object"
      || Array.isArray(state.legacyCoreLevels)
      || Object.keys(state.legacyCoreLevels).length !== Object.keys(this.coreSpecs).length) invalid();
    let spent = 0;
    for (const [key, spec] of Object.entries(this.coreSpecs)) {
      const level = state.coreLevels[key];
      if (!Number.isInteger(level) || level < 0 || level > spec.maxLevel
        || (level > 0 && state.completedPlanets < spec.unlockResets)) invalid();
      const oldLevel = state.legacyCoreLevels[key];
      const oldPrice = this.data.prestige?.legacyCorePrices?.[key];
      if (!Number.isInteger(oldLevel) || oldLevel < 0 || oldLevel > level
        || oldLevel > (oldPrice?.[2] || 0)) invalid();
      for (let i = 0; i < level; i += 1) spent += i < oldLevel
        ? oldPrice[0] * oldPrice[1] ** i : spec.baseCost * spec.costGrowth ** i;
    }
    const rewardStep = this.data.prestige?.rewardStep || 1;
    const q = Math.floor(state.completedPlanets / rewardStep); const r = state.completedPlanets % rewardStep;
    const earned = state.completedPlanets + rewardStep * q * (q - 1) / 2 + q * r;
    if (!Number.isSafeInteger(earned) || state.cores + spent !== earned
      || !Array.isArray(state.planetHistory)
      || state.planetHistory.length !== Math.min(state.completedPlanets, this.data.prestige?.historyLimit || 20)
      || state.planetHistory.some((item, index, history) => !item
        || item.planet !== state.completedPlanets - history.length + index + 1
        || !Number.isFinite(item.minutes) || item.minutes <= 0
        || !Number.isFinite(item.completedMinute) || item.completedMinute > state.minute + 1e-7
        || item.completedMinute + 1e-7 < item.minutes
        || (index > 0 && item.completedMinute + 1e-7 < history[index - 1].completedMinute + item.minutes)
        || item.reward !== 1 + Math.floor((item.planet - 1) / rewardStep)
        || (item.allMaxedMinute !== null && (!Number.isFinite(item.allMaxedMinute)
          || item.allMaxedMinute + 1e-7 < item.completedMinute - item.minutes || item.allMaxedMinute > item.completedMinute + 1e-7)))) invalid();
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
        || state.manualLevels[key] > Math.max(0, this.specs[key].manualTarget - state.resets)) invalid();
    }
    for (const field of ["autoUnlocked", "everKeys"]) {
      if (!Array.isArray(state[field]) || state[field].some((key) => !Object.hasOwn(this.specs, key))
        || new Set(state[field]).size !== state[field].length) invalid();
    }
    if (this.localKeys.some((key) => {
      const target = Math.max(0, this.specs[key].manualTarget - state.resets);
      const automated = this.specs[key].status === "active" && (target === 0
        ? state.levels[key] > 0 : state.manualLevels[key] === target);
      return state.manualLevels[key] > state.levels[key] || state.autoUnlocked.includes(key) !== automated;
    })) invalid();
    const report = state.lastHelperReport;
    if (report !== null && (!report || !Array.isArray(report.items)
      || !Number.isInteger(report.minute) || report.minute < 0 || report.minute > state.minute
      || report.levels !== report.items.length || !Number.isFinite(report.spent) || report.spent < 0
      || report.items.some((item) => !item || !Object.hasOwn(this.specs, item.key)
        || !Number.isInteger(item.level) || item.level <= 0 || !Number.isFinite(item.cost) || item.cost < 0))) invalid();
    state.contentVersion = this.data.contentVersion;
    this.rng.restore(saved.rng);
    this.state = state;
    this._voyage = null; this._canonicalVoyage = null;
  }
  level(key) { return Number(this.state.levels[key] || 0); }
  manualTarget(key) { return Math.max(0, this.specs[key].manualTarget - this.state.resets); }
  coreEffect(kind) {
    return Object.values(this.coreSpecs).reduce((sum, spec) =>
      sum + (spec.effectKind === kind ? spec.effectPerLevel * this.state.coreLevels[spec.key] : 0), 0);
  }
  prestigeSpeed() {
    return (1 + this.coreEffect("global_linear")) * 2 ** this.coreEffect("global_speed");
  }
  coreCost(key) {
    const spec = this.coreSpecs[key];
    return spec ? spec.baseCost * spec.costGrowth ** this.state.coreLevels[key] : Infinity;
  }
  coreAvailable(key) {
    const spec = this.coreSpecs[key];
    return Boolean(spec && this.state.completedPlanets >= spec.unlockResets && this.state.coreLevels[key] < spec.maxLevel);
  }
  purchaseCore(key) {
    if (!this.coreAvailable(key)) return { ok: false, reason: "locked" };
    const cost = this.coreCost(key);
    if (this.state.cores < cost) return { ok: false, reason: "cores" };
    this.state.cores -= cost; this.state.coreLevels[key] += 1;
    this._voyage = null;
    return { ok: true, key, cost, level: this.state.coreLevels[key] };
  }
  coreRouteSpecs() {
    return Object.values(this.coreSpecs).filter((spec) => this.state.coreAutoRoute !== "off");
  }
  coreRouteScore(spec) {
    const preferences = {
      speed: ["global_linear", "global_speed", "speed_strength"],
      rebuild: ["income_strength", "local_discount", "equipment_strength"],
      burst: ["opening_burst", "global_speed", "completion_depth"],
    };
    return this.coreCost(spec.key) / (this.state.completedPlanets >= 10
      && preferences[this.state.coreAutoRoute]?.includes(spec.effectKind) ? 4 : 1);
  }
  autoPurchaseCore() {
    const purchases = [];
    for (;;) {
      const spec = this.coreRouteSpecs().filter((item) => this.coreAvailable(item.key))
        .sort((a, b) => this.coreRouteScore(a) - this.coreRouteScore(b))[0];
      if (!spec || this.coreCost(spec.key) > this.state.cores) return purchases;
      purchases.push(this.purchaseCore(spec.key));
    }
  }
  setCoreAutoRoute(route) {
    if (!["off", "balanced", "speed", "rebuild", "burst"].includes(route)) throw new Error("Invalid core automation route");
    this.state.coreAutoRoute = route;
    return this.autoPurchaseCore();
  }
  galaxyComplete() { return this.state.completedPlanets >= (this.data.prestige?.galaxyTargetPlanets ?? 1000000); }
  setAutoDepart(enabled) {
    if (typeof enabled !== "boolean") throw new Error("Auto departure setting must be boolean");
    this.state.autoDepart = enabled;
  }
  allLocalMaxed() {
    return this.localKeys.every((key) => this.specs[key].status !== "active" || this.level(key) === this.specs[key].maxLevel);
  }
  finishPlanet() {
    const s = this.state;
    if (!this.data.prestige || s.planetComplete || s.depth < s.targetDepth) return false;
    const reward = 1 + Math.floor(s.resets / this.data.prestige.rewardStep);
    s.depth = s.targetDepth; s.planetComplete = true; s.completedPlanets += 1; s.cores += reward;
    s.planetHistory.push({ planet: s.completedPlanets, minutes: s.minute - s.planetStartedMinute,
      completedMinute: s.minute, reward, allMaxedMinute: s.allMaxedMinute });
    s.planetHistory = s.planetHistory.slice(-this.data.prestige.historyLimit);
    return true;
  }
  departPlanet() {
    const s = this.state;
    if (this.galaxyComplete()) return { ok: false, reason: "galaxy" };
    if (!s.planetComplete) return { ok: false, reason: "unfinished" };
    s.resets += 1; s.planetComplete = false;
    this.clearLocalPlanet();
    return { ok: true };
  }
  clearLocalPlanet() {
    const s = this.state;
    s.depth = 0; s.credits = 0;
    s.levels = objectOf(this.localKeys); s.manualLevels = objectOf(this.localKeys);
    s.autoUnlocked = []; s.everKeys = []; s.eraFirstDays = {}; s.autoCursor = 0;
    s.lastHelperReport = null; s.planetStartedMinute = s.minute; s.allMaxedMinute = null;
    this._voyage = null;
  }
  effectStrength(kind) {
    if (kind === "speed_compound") return 1 + this.coreEffect("speed_strength");
    if (kind === "crit_chance") return 1;
    let strength = 1 + this.coreEffect("equipment_strength");
    if (kind === "income" || kind === "shift_relay") strength *= 1 + this.coreEffect("income_strength");
    if (kind === "extra_depth" || kind === "penetration") strength *= 1 + this.coreEffect("depth_strength");
    return strength;
  }
  costFor(key, level = this.level(key)) {
    const spec = this.specs[key]; return Number(spec.baseCost) * Number(spec.costGrowth) ** level / (1 + this.coreEffect("local_discount"));
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
    return [...this.eraSequence].reverse().find((era) => this.eraByKey[era].status !== "reserve" && this.eraUnlocked(era)) || this.eraSequence[0];
  }
  available(key, automatic = false) {
    const spec = this.specs[key];
    if (!spec || this.state.planetComplete || this.level(key) >= spec.maxLevel || spec.status !== "active") return false;
    if (automatic && this.manualTarget(key) > 0 && !this.state.autoUnlocked.includes(key)) return false;
    if (!automatic && this.state.manualLevels[key] >= this.manualTarget(key)) return false;
    return this.eraUnlocked(spec.era) && this.state.depth >= Number(spec.unlockDepth)
      && spec.prerequisites.every((required) => this.level(required) >= 1);
  }
  manualCandidates() { return this.localKeys.filter((key) => this.available(key)); }
  reserveCost() {
    const costs = [];
    this.manualCandidates().forEach((key) => {
      const spec = this.specs[key];
      const remaining = this.manualTarget(key) - this.state.manualLevels[key];
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
    this._voyage = null;
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
      if (this.state.manualLevels[key] === this.manualTarget(key)) {
        if (!this.state.autoUnlocked.includes(key)) this.state.autoUnlocked.push(key);
        if (!(this.specs[key].era in this.state.eraFirstDays)) this.state.eraFirstDays[this.specs[key].era] = this.state.day;
      }
    }
    if (automatic && this.manualTarget(key) === 0 && !this.state.autoUnlocked.includes(key)) {
      this.state.autoUnlocked.push(key);
      if (!(this.specs[key].era in this.state.eraFirstDays)) this.state.eraFirstDays[this.specs[key].era] = this.state.day;
    }
    if (this.state.allMaxedMinute === null && this.allLocalMaxed()) this.state.allMaxedMinute = this.state.minute;
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
      totals[kind] = (totals[kind] || 0) + Number(this.specs[key].effectPerLevel) * level * this.effectStrength(kind);
    });
    return totals;
  }
  multiplierBreakdown() {
    const e = this.effectLevels();
    let speed = 1;
    this.localKeys.forEach((key) => {
      const level = this.level(key); const spec = this.specs[key];
      if (level && spec.effectKind === "speed_compound") speed *= (1 + Number(spec.effectPerLevel) * this.effectStrength(spec.effectKind)) ** level;
    });
    const parallel = 1 + (e.parallel || 0); const cats = 1 + (e.cats || 0);
    const sharpness = 1 + (e.sharpness || 0); const fragility = 1 + (e.fragility || 0);
    const income = 1 + (e.income || 0); const extraDepth = 1 + (e.extra_depth || 0);
    const critChance = Math.min(0.65, e.crit_chance || 0); const critDamage = Number(this.rules.baseCriticalDamage) + (e.crit_damage || 0);
    const critical = 1 + critChance * critDamage;
    const catLevels = this.localKeys.reduce((sum, key) => sum + (this.specs[key].effectKind === "cats" ? this.level(key) : 0), 0);
    const coordination = 1 + (e.coordination || 0) * catLevels;
    const localMinute = this.state.minute - this.state.planetStartedMinute;
    const teamwork = 1 + (e.teamwork || 0) * Math.sqrt(Math.max(0, localMinute / 1440));
    const momentum = 1 + (e.momentum || 0) * Math.min(1, (localMinute % 1440) / 240);
    const autoCount = this.state.autoUnlocked.length;
    const resonance = 1 + (e.resonance || 0) * autoCount;
    const shiftRelay = 1 + (e.shift_relay || 0) * autoCount;
    const penetration = 1 + (e.penetration || 0) * Math.max(0, critical - 1);
    return {
      speed, parallel, cats, sharpness, fragility, income, extra_depth: extraDepth,
      critical, coordination, teamwork, momentum, resonance, shift_relay: shiftRelay,
      penetration, prestige: this.prestigeSpeed(), stellar_relay: 1 + this.coreEffect("line_synergy") * autoCount,
      opening_burst: localMinute < (this.data.prestige?.openingBurstSeconds || 1) / 60 ? 1 + this.coreEffect("opening_burst") : 1,
      completion_depth: this.allLocalMaxed() ? 1 + this.coreEffect("completion_depth") : 1,
    };
  }
  incomeMultiplier() {
    const f = this.multiplierBreakdown();
    return ["speed", "parallel", "cats", "sharpness", "fragility", "critical", "coordination", "teamwork", "momentum", "resonance", "income", "shift_relay", "prestige", "stellar_relay", "opening_burst"].reduce((product, key) => product * f[key], 1);
  }
  depthMultiplier() {
    const f = this.multiplierBreakdown();
    return ["speed", "parallel", "cats", "sharpness", "fragility", "critical", "coordination", "teamwork", "momentum", "resonance", "extra_depth", "penetration", "prestige", "stellar_relay", "opening_burst", "completion_depth"].reduce((product, key) => product * f[key], 1);
  }
  autoPurchase() {
    if (this.state.resets > 0) {
      const bought = [];
      const maximum = this.localKeys.reduce((sum, key) => sum + this.specs[key].maxLevel, 0);
      const budget = this.state.resets >= 3 ? maximum : Math.min(maximum,
        Math.ceil(this.prestigeSpeed() * this.rules.autoPurchaseBudget));
      // Re-scan after each paid purchase so level-zero automation can unlock its real prerequisites.
      for (let i = 0; i < budget; i += 1) {
        const candidates = this.localKeys.filter((key) => this.available(key, true))
          .sort((a, b) => this.costFor(a) - this.costFor(b) || a.localeCompare(b));
        const key = candidates.find((key) => this.state.credits - this.costFor(key) + 1e-9 >= this.reserveCost());
        if (!key) break;
        const result = this.purchase(key, true);
        if (!result.ok) break;
        bought.push(result);
      }
      return bought;
    }
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
  voyagePlan() {
    const s = this.state;
    const key = JSON.stringify([s.coreLevels, s.targetDepth]);
    if (this._voyage?.key === key) return this._voyage.plan;
    const fresh = s.depth === 0 && s.credits === 0 && this.localKeys.every((k) => !s.levels[k]);
    let plan;
    if (fresh && this._canonicalVoyage?.key === key) plan = this._canonicalVoyage.plan;
    else {
      const scratch = new S2Engine(this.data);
      scratch.state = structuredClone(s);
      scratch.state.minute = s.minute - s.planetStartedMinute;
      scratch.state.planetStartedMinute = 0;
      scratch.state.allMaxedMinute = s.allMaxedMinute === null ? null : s.allMaxedMinute - s.planetStartedMinute;
      plan = compileVoyage(scratch);
      this.lastBatchSummary.compiled += 1;
      this.lastBatchSummary.events += plan.events.length;
      if (fresh) this._canonicalVoyage = { key, plan };
    }
    this._voyage = { key, plan };
    return plan;
  }
  syncVoyageClock(minute) {
    const s = this.state;
    s.minute = minute; this.startNewDay();
    s.nextAutoMinute = (Math.floor(minute / this.rules.autoPurchaseIntervalMinutes) + 1) * this.rules.autoPurchaseIntervalMinutes;
    const lastMidnight = Math.floor(minute / 1440) * 1440;
    if (lastMidnight >= s.nextHelperMinute && lastMidnight >= s.planetStartedMinute) {
      s.lastHelperReport = { minute: lastMidnight, levels: 0, spent: 0, items: [] };
    }
    s.nextHelperMinute = lastMidnight + 1440;
  }
  applyVoyageSample(plan, age) {
    const s = this.state; const sample = sampleVoyage(plan, age);
    const beforeLevels = s.levels;
    const before = this.localKeys.reduce((n, key) => n + s.levels[key], 0);
    const previousAge = s.minute - s.planetStartedMinute;
    s.totalAutoLevels += sample.built - before;
    s.depth = Math.min(s.targetDepth, sample.depth); s.credits = sample.credits;
    s.levels = { ...sample.levels }; s.manualLevels = { ...sample.manualLevels };
    s.autoUnlocked = [...sample.autoUnlocked]; s.everKeys = [...sample.everKeys];
    for (const [era, time] of Object.entries(sample.eraAges)) s.eraFirstDays[era] = Math.floor((s.planetStartedMinute + time) / 1440) + 1;
    s.allMaxedMinute = sample.allMaxedAge === null ? null : s.planetStartedMinute + sample.allMaxedAge;
    // Detailed events are only retained for the partial voyage, never expanded
    // for a batch. Lifetime counts and the batch summary remain exact.
    for (const event of plan.events) {
      if (event.age >= previousAge && event.age <= age && event.level > beforeLevels[event.key]) {
        if (this.lastBlockEvents.length < 1024) this.lastBlockEvents.push({ ...event, minute: s.planetStartedMinute + event.age });
      }
    }
    this.syncVoyageClock(s.planetStartedMinute + age);
  }
  planetsUntilCorePurchase(limit) {
    const s = this.state;
    const specs = this.coreRouteSpecs().filter((spec) => s.coreLevels[spec.key] < spec.maxLevel);
    if (!specs.length) return limit;
    // An unlock may change the savings target. Never binary-search across it.
    for (const spec of specs) {
      if (spec.unlockResets > s.completedPlanets) limit = Math.min(limit, spec.unlockResets - s.completedPlanets);
    }
    const target = specs.filter((spec) => this.coreAvailable(spec.key))
      .sort((a, b) => this.coreRouteScore(a) - this.coreRouteScore(b))[0];
    if (!target) return limit;
    const step = this.data.prestige.rewardStep;
    const earned = earnedCores(s.completedPlanets, step);
    const canBuy = (count) => s.cores + earnedCores(s.completedPlanets + count, step) - earned >= this.coreCost(target.key);
    if (!canBuy(limit)) return limit;
    let lo = 1; let hi = limit;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (canBuy(mid)) hi = mid; else lo = mid + 1;
    }
    return lo;
  }
  settleVoyages(plan, count) {
    const s = this.state; const first = s.completedPlanets; const start = s.minute;
    const step = this.data.prestige.rewardStep;
    const finish = start + plan.duration * count;
    const finalPlanet = first + count;
    s.cores += earnedCores(finalPlanet, step) - earnedCores(first, step);
    s.totalAutoLevels += count * plan.end.built;
    const history = s.planetHistory;
    for (let i = Math.max(1, count - this.data.prestige.historyLimit + 1); i <= count; i += 1) {
      history.push({ planet: first + i, minutes: plan.duration, completedMinute: start + i * plan.duration,
        reward: 1 + Math.floor((first + i - 1) / step),
        allMaxedMinute: plan.end.allMaxedAge === null ? null : start + (i - 1) * plan.duration + plan.end.allMaxedAge });
    }
    s.planetHistory = history.slice(-this.data.prestige.historyLimit);
    s.completedPlanets = finalPlanet;
    this.syncVoyageClock(finish);
    const parked = !s.autoDepart || this.galaxyComplete();
    s.resets = finalPlanet - Number(parked);
    s.planetComplete = parked;
    if (parked) {
      s.planetStartedMinute = start + (count - 1) * plan.duration;
      s.levels = { ...plan.end.levels }; s.manualLevels = { ...plan.end.manualLevels };
      s.depth = s.targetDepth; s.credits = plan.end.credits;
      s.autoUnlocked = [...plan.end.autoUnlocked]; s.everKeys = [...plan.end.everKeys];
      s.eraFirstDays = Object.fromEntries(Object.entries(plan.end.eraAges)
        .map(([era, age]) => [era, Math.floor((s.planetStartedMinute + age) / 1440) + 1]));
      s.allMaxedMinute = plan.end.allMaxedAge === null ? null : s.planetStartedMinute + plan.end.allMaxedAge;
      const midnight = Math.floor(finish / 1440) * 1440;
      s.lastHelperReport = midnight >= s.planetStartedMinute
        ? { minute: midnight, levels: 0, spent: 0, items: [] } : null;
    } else this.clearLocalPlanet();
    this.lastBatchSummary.planets += count;
    this.autoPurchaseCore();
  }
  advanceVoyages(endMinute) {
    const s = this.state;
    let boundaries = 0;
    const maxBoundaries = Object.values(this.coreSpecs).reduce((n, spec) => n + spec.maxLevel + 2, 0) + 8;
    while (s.minute < endMinute) {
      if (++boundaries > maxBoundaries) throw new Error("Permanent event budget exceeded");
      if (s.planetComplete) {
        if (!s.autoDepart || s.resets === 0 || this.galaxyComplete()) {
          this.syncVoyageClock(endMinute); return;
        }
        this.departPlanet();
      }
      const plan = this.voyagePlan();
      const remaining = endMinute - s.minute;
      const age = s.minute - s.planetStartedMinute;
      if (age === 0 && plan.initialAge === 0) {
        let count = Math.floor(remaining / plan.duration);
        count = Math.min(count, this.data.prestige.galaxyTargetPlanets - s.completedPlanets);
        if (!s.autoDepart) count = Math.min(count, 1);
        if (count > 0) {
          count = this.planetsUntilCorePurchase(count);
          this.settleVoyages(plan, count);
          continue;
        }
      }
      const endAge = Math.min(plan.duration, endMinute - s.planetStartedMinute);
      this.applyVoyageSample(plan, endAge);
      if (endAge >= plan.duration) {
        s.depth = s.targetDepth;
        this.finishPlanet();
        this.lastBatchSummary.planets += 1;
        this.autoPurchaseCore();
        if (s.autoDepart && !this.galaxyComplete()) this.departPlanet();
      } else {
        this.syncVoyageClock(endMinute);
        return;
      }
    }
  }
  mineBlock(minutes = Number(this.rules.settlementMinutes), deterministic = false) {
    const step = Number(this.rules.settlementMinutes);
    const endMinute = this.state.minute + minutes;
    if (!Number.isFinite(minutes) || minutes <= 0 || endMinute > Number.MAX_SAFE_INTEGER
      || endMinute <= this.state.minute
      || (this.state.resets < 3 && (!Number.isSafeInteger(minutes) || minutes % step
        || !Number.isSafeInteger(endMinute)))) throw new Error("mineBlock must use settlement-sized minutes before full automation");
    const bought = [];
    this.lastBlockEvents = [];
    this.lastBatchSummary = { planets: 0, compiled: 0, events: 0 };
    while (this.state.minute < endMinute) {
      if (this.state.resets >= 3) { this.advanceVoyages(endMinute); break; }
      if (!this.state.planetComplete) {
        const noise = deterministic ? 1 : clamp(this.rng.gauss(1, Number(this.rules.randomSigma)), 0.85, 1.15);
        const depthRate = Number(this.rules.baseDepthPerMinute) * this.depthMultiplier() * noise;
        const miningMinutes = this.data.prestige ? Math.max(0, Math.min(step, (this.state.targetDepth - this.state.depth) / depthRate)) : step;
        this.state.credits += Number(this.rules.baseCreditsPerMinute) * this.incomeMultiplier() * miningMinutes * noise;
        this.state.depth += depthRate * miningMinutes;
        if (this.data.prestige && miningMinutes < step) this.state.depth = this.state.targetDepth;
      }
      this.state.minute += step;
      this.startNewDay();
      if (this.finishPlanet()) this.autoPurchaseCore();
      if (this.state.resets > 0) {
        const purchases = this.autoPurchase();
        bought.push(...purchases);
        this.lastBlockEvents.push(...purchases.map((item) => ({ ...item, minute: this.state.minute })));
      }
      while (this.state.minute >= this.state.nextAutoMinute) {
        const purchases = this.state.resets === 0 ? this.autoPurchase() : [];
        bought.push(...purchases);
        this.lastBlockEvents.push(...purchases.map((item) => ({ ...item, minute: this.state.minute })));
        this.state.nextAutoMinute += Number(this.rules.autoPurchaseIntervalMinutes);
      }
      while (this.state.minute >= this.state.nextHelperMinute) {
        this.lastBlockEvents.push(...this.helperPurchase().map((item) => ({ ...item, minute: this.state.minute })));
        this.state.nextHelperMinute += Number(this.rules.helperIntervalMinutes);
      }
      if (this.state.planetComplete && this.state.resets > 0 && this.state.autoDepart && !this.galaxyComplete()) this.departPlanet();
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
      const depthKinds = new Set(["speed_compound", "parallel", "cats", "sharpness", "fragility", "crit_chance", "crit_damage", "coordination", "teamwork", "momentum", "resonance", "extra_depth", "penetration"]);
      const incomeKinds = new Set([...depthKinds].filter((key) => !["extra_depth", "penetration"].includes(key)).concat(["income", "shift_relay"]));
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
