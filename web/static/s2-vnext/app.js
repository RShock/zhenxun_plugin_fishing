(() => {
  "use strict";

  const SAVE_KEY = "s2-vnext-browser-save-v1";
  const TARGET_DEPTH = 600_000_000_000;
  const ORES = [
    { key: "tin", name: "锡矿", icon: "Sn", color: "tin", value: 1 },
    { key: "copper", name: "铜矿", icon: "Cu", color: "copper", value: 2.8 },
    { key: "quartz", name: "紫晶", icon: "Qz", color: "quartz", value: 9 },
    { key: "gold", name: "金猫锭", icon: "Au", color: "gold", value: 32 },
    { key: "coreshard", name: "虹核晶", icon: "◇", color: "coreshard", value: 120 },
  ];
  const ERA_LIST = [
    { key: "foundation", name: "基础工程", short: "基础", unlock: 0 },
    { key: "industrial", name: "工业时代", short: "工业", unlock: 0.00001 },
    { key: "electrical", name: "电力时代", short: "电力", unlock: 0.00003 },
    { key: "modern", name: "现代时代", short: "现代", unlock: 0.00007 },
    { key: "future", name: "未来时代", short: "未来", unlock: 0.00015 },
    { key: "planetary", name: "行星时代", short: "行星", unlock: 0.02 },
    { key: "anomaly", name: "异常科技", short: "异常", unlock: 0.08 },
  ];
  const SPECIAL_UNLOCK_DELAY = 0.00002;
  const SPECIAL_BURST_THRESHOLD = 0.005;
  const SPECIALS = [
    "relativity_burst", "phase_skip", "singularity_finish", "ore_echo", "time_dilation",
    "entropy_guard", "quantum_tunnel", "gravity_sling", "cat_overclock", "core_resonance",
    "parallel_bore", "vacuum_cache",
  ];
  const SPECIAL_NAMES = {
    relativity_burst: "相对论爆发", phase_skip: "相位跳跃", singularity_finish: "奇点收尾",
    ore_echo: "矿脉回响", time_dilation: "时间膨胀", entropy_guard: "熵减防护",
    quantum_tunnel: "量子隧穿", gravity_sling: "引力弹弓", cat_overclock: "猫群超频",
    core_resonance: "核心共振", parallel_bore: "平行钻孔", vacuum_cache: "真空缓存",
  };
  const EFFECTS = [
    ["speed_add", 0.1, "推进效率"], ["depth_efficiency", 0.012, "深度效率"],
    ["yield_add", 0.018, "矿物产量"], ["credit_add", 0.02, "矿币收益"],
    ["carry_add", 0.022, "携带量"], ["rare_find", 0.004, "稀有发现"],
    ["ore_value", 0.015, "矿石价值"], ["noise_reduction", 0.006, "扰动稳定"],
    ["crit_chance", 0.003, "暴击概率"], ["crit_power", 0.012, "暴击倍率"],
    ["salvage", 0.025, "回收收益"], ["cat_sync", 0.01, "猫群协同"],
  ];
  const NAMES = {
    foundation: ["地质罗盘", "猫爪耐磨层", "手摇绞盘", "碎石筛分台", "矿灯电池", "双路通风", "水压排渣", "安全绳网", "回收熔炉", "应急猫粮", "地层标记", "便携矿仓", "低温冷却", "矿脉听诊", "基础测绘", "矿车轴承"],
    industrial: ["高压爆破", "定向炸药", "蒸汽活塞", "锅炉绝热", "重型铰链", "钢轨铺设", "矿渣压块", "工业除尘", "液压支架", "连续装载", "熔炉增压", "耐热猫爪", "矿井升降机", "燃料回收", "爆破时序", "工业安全协议"],
    electrical: ["电磁钻头", "三相供能", "蓄电矿车", "绝缘猫服", "电弧熔炼", "高频震岩", "智能照明", "电网调度", "电容脉冲", "矿石电析", "感应雷达", "电机冷却", "远程断路", "备用电池", "电磁吊臂", "电力回收"],
    modern: ["全断面掘进", "激光测距", "无人运输", "液氮破岩", "模块化钻臂", "智能排水", "岩层预测", "材料复合", "超硬刀头", "自动换头", "矿尘净化", "地下中继", "机械臂编队", "应力平衡", "精密取样", "现代安全网"],
    future: ["纳米钻群", "量子定位", "相位切割", "真空输送", "拓扑矿车", "引力补偿", "光子熔炼", "冷核供能", "猫群神经链", "概率采样", "时间标记", "空间折叠", "暗能量电池", "量子回收", "奇点预警", "未来工厂"],
    planetary: ["行星地壳扫描", "地核共振", "潮汐钻井", "磁场牵引", "地幔导流", "星球环轨", "重力矿车", "地核散热", "行星级猫群", "熔岩隔离", "极点同步", "核心护盾", "地质时间压缩", "星球裂隙", "引力透镜", "行星工厂"],
    anomaly: ["相对论回响", "宏观量子纠缠", "真空涨落", "因果回收", "时间膨胀舱", "奇点穿刺", "熵减协议", "多维猫爪", "虚数矿脉", "观测者偏置", "宇宙弦牵引", "反物质排渣", "无穷压缩", "星门装载", "宇宙背景采样", "终极挖掘许可"],
  };
  const CORE_SPECS = [
    { key: "planetary_power", name: "行星之力", max: 100, cost: 1, effect: "每级 +1.00 全局速度，首级使下一轮速度翻倍" },
    { key: "stage_skip", name: "阶段跳过", max: 20, cost: 2, effect: "每级减少 8% 星球深度需求，最低保留 2%" },
    { key: "core_survey", name: "核心勘探", max: 50, cost: 3, effect: "每次爆星额外获得 1 核心" },
    { key: "entanglement", name: "宏观量子纠缠", max: 40, cost: 5, effect: "爆星时有额外星球被同时摧毁" },
    { key: "auto_all", name: "全自动采购", max: 1, cost: 8, effect: "所有本地科技获得自动采购资格" },
    { key: "core_quantum", name: "核心量子加速", max: 50, cost: 8, effect: "每级 +1.50 全局速度" },
  ];

  const baseSpecs = [
    // 初始资源只支持做出一条明确选择；达到 3 级后自动采购再接管成长，避免 D1 手动刷满四条基础线。
    ["pickaxe", "矿镐", 100, { credits: 500 }, 1.34, 0, "speed_add", 0.35, "每级 +0.35 基础挖掘力"],
    ["cart", "矿车", 100, { credits: 750 }, 1.35, 0, "carry_add", 0.04, "每级 +0.04 携带量"],
    ["refinery", "矿石精炼", 100, { credits: 1100 }, 1.36, 0, "credit_add", 0.22, "每级 +0.22 精炼收益"],
    ["survey", "洞穴勘探", 100, { credits: 1500 }, 1.37, 0, "speed_add", 0.25, "每级 +0.25 推进效率"],
    ["cat", "猫矿工", 12, { credits: 1500 }, 2.8, 0, "cat_sync", 0.03, "每级复制一份基础挖掘数据"],
    ["industrial_blaster", "爆破镐", 40, { credits: 12000, copper: 50000 }, 1.43, 0.00001, "speed_add", 0.30, "每级 +0.30 推进效率"],
    ["steam_cart", "蒸汽矿车", 40, { credits: 15000, copper: 65000 }, 1.43, 0.00001, "carry_add", 0.05, "每级 +0.05 携带量"],
    ["electric_pickaxe", "电动镐", 40, { credits: 80000, quartz: 80000 }, 1.47, 0.00003, "speed_add", 0.55, "每级 +0.55 基础挖掘力"],
    ["electric_cart", "电力车", 40, { credits: 90000, quartz: 90000 }, 1.47, 0.00003, "carry_add", 0.08, "每级 +0.08 携带量"],
    ["modern_drill", "掘进机", 40, { credits: 500000, gold: 50000 }, 1.50, 0.00007, "speed_add", 0.90, "每级 +0.90 推进效率"],
    ["future_quantum", "微观量子挖掘", 30, { credits: 4000000, gold: 200000, coreshard: 20000 }, 1.55, 0.00015, "speed_add", 1.50, "每级 +1.50 推进效率"],
    ["relativity", "相对论效应", 10, { credits: 2e6, coreshard: 40 }, 1.72, 0.080005, "none", 0, "重生后 60 秒速度 ×100", "relativity_burst"],
  ];

  const specs = {};
  const localKeys = [];
  const coreKeys = CORE_SPECS.map((item) => item.key);
  const specialForIndex = (eraIndex, index) => index % 4 === 0 ? SPECIALS[(index / 4 + eraIndex) % SPECIALS.length] : "";
  baseSpecs.forEach((item) => {
    const [key, name, max, cost, growth, unlock, effectKind, perLevel, effect, special = ""] = item;
    specs[key] = { key, name, max, cost, growth, unlock, era: key === "relativity" ? "anomaly" : key === "industrial_blaster" || key === "steam_cart" ? "industrial" : key === "electric_pickaxe" || key === "electric_cart" ? "electrical" : key === "modern_drill" ? "modern" : key === "future_quantum" ? "future" : "foundation", effectKind, perLevel, effect, special, secondaryKind: "none", secondaryPerLevel: 0, prerequisites: [] };
    localKeys.push(key);
  });
  ERA_LIST.forEach((era, eraIndex) => {
    NAMES[era.key].forEach((name, index) => {
      const key = `${era.key}_${String(index + 1).padStart(2, "0")}`;
      const [effectKind, basePer, label] = EFFECTS[(index + eraIndex * 3) % EFFECTS.length];
      const special = specialForIndex(eraIndex, index);
      const secondary = index % 3 === 0 ? EFFECTS[(index * 2 + eraIndex + 5) % EFFECTS.length] : null;
      const perLevel = basePer * (1 + eraIndex * .08 + index * .006);
      specs[key] = {
        key, name, max: 8 + ((index + eraIndex) % 5), cost: eraCost(era.key), growth: 1.30 + eraIndex * .025 + (index % 3) * .015,
        unlock: era.unlock + (special ? SPECIAL_UNLOCK_DELAY : 0), era: era.key, effectKind, perLevel,
        effect: `每级 +${trim(perLevel)} ${label}${secondary ? `；+${trim(secondary[1] * (1 + eraIndex * .05))} ${secondary[2]}` : ""}`,
        special, secondaryKind: secondary ? secondary[0] : "none", secondaryPerLevel: secondary ? secondary[1] * (1 + eraIndex * .05) : 0,
        // 顺序由时代门槛和资源成本表达；特殊节点不能把同一时代的科技树截断成前三项。
        prerequisites: [],
      };
      localKeys.push(key);
    });
  });

  function eraCost(era) {
    return {
      foundation: { credits: 180, tin: 500 }, industrial: { credits: 12000, copper: 50000 }, electrical: { credits: 80000, quartz: 80000 },
      modern: { credits: 500000, gold: 50000 }, future: { credits: 4000000, gold: 200000, coreshard: 20000 },
      planetary: { credits: 50000000, gold: 1000000, coreshard: 100000 }, anomaly: { credits: 500000000, coreshard: 500000 },
    }[era];
  }
  function trim(value) { return Number(value.toFixed(3)).toString(); }

  function newState() {
    const localLevels = Object.fromEntries(localKeys.map((key) => [key, 0]));
    const permanentLevels = Object.fromEntries(coreKeys.map((key) => [key, 0]));
    return {
      version: 1, totalMinutes: 0, depth: 0, targetDepth: TARGET_DEPTH, planets: 0, cores: 0,
      resources: { credits: 0, tin: 0, copper: 0, quartz: 0, gold: 0, coreshard: 0 },
      localLevels, permanentLevels, autoUnlocked: [], everLocalKeys: [], resetDays: [],
      dailyMessages: 0, totalMessages: 0, speedChoice: 1, events: [], maxSpeed: 1,
      burstSeconds: 0, selectedEra: "foundation", running: false,
    };
  }

  let state = newState();
  let renderQueued = false;
  let saveTimer = null;
  let toastTimer = null;

  const $ = (id) => document.getElementById(id);
  const els = {
    cacheState: $("cacheState"), runState: $("runState"), eraName: $("eraName"), depthValue: $("depthValue"),
    targetDepth: $("targetDepth"), depthProgress: $("depthProgress"), progressLabel: $("progressLabel"), speedLabel: $("speedLabel"),
    planetCount: $("planetCount"), coreCount: $("coreCount"), coreValue: $("coreValue"), resourceStrip: $("resourceStrip"),
    techCount: $("techCount"), eraTabs: $("eraTabs"), techSearch: $("techSearch"), techSummary: $("techSummary"), techList: $("techList"),
    coreList: $("coreList"), eventLog: $("eventLog"), runBtn: $("runBtn"), runIcon: $("runIcon"), runText: $("runText"),
    saveMeta: $("saveMeta"), toast: $("toast"), drillBeam: $("drillBeam"),
  };

  function progress() { return Math.max(0, Math.min(1, state.depth / state.targetDepth)); }
  function day() { return 1 + Math.floor(state.totalMinutes / 1440); }
  function minuteOfDay() { return state.totalMinutes % 1440; }
  function formatNumber(value, decimals = 2) {
    if (!Number.isFinite(value)) return "∞";
    const abs = Math.abs(value);
    if (abs === 0) return "0";
    if (abs < 1000) return value.toFixed(decimals).replace(/\.00$/, "");
    if (abs < 1e6) return Math.round(value).toLocaleString("zh-CN");
    const exponent = Math.floor(Math.log10(abs));
    const mantissa = value / (10 ** exponent);
    return `${mantissa.toFixed(2).replace(/\.00$/, "")}e${exponent}`;
  }
  function formatPercent(value) { return `${(value * 100).toFixed(value < .01 ? 3 : 2)}%`; }
  function formatDuration(minutes) {
    if (minutes < 60) return `${Math.round(minutes)} 分钟`;
    if (minutes < 1440) return `${(minutes / 60).toFixed(1)} 小时`;
    return `${(minutes / 1440).toFixed(1)} 天`;
  }
  function currentEra() {
    return ERA_LIST.slice().reverse().find((era) => progress() >= era.unlock) || ERA_LIST[0];
  }
  function resourceTotal(key) { return state.resources[key] || 0; }
  function costAt(spec, level, amount = 1) {
    const result = {};
    for (let offset = 0; offset < amount; offset += 1) {
      const multiplier = spec.growth ** (level + offset);
      Object.entries(spec.cost).forEach(([key, value]) => { result[key] = (result[key] || 0) + value * multiplier; });
    }
    return result;
  }
  function costText(cost) { return Object.entries(cost).map(([key, value]) => `${resourceLabel(key)} ${formatNumber(value, 0)}`).join(" · "); }
  function resourceLabel(key) { return key === "credits" ? "矿币" : (ORES.find((item) => item.key === key)?.name || key); }
  function sumEffects() {
    const result = {};
    localKeys.forEach((key) => {
      const spec = specs[key]; const level = state.localLevels[key] || 0;
      if (!level) return;
      if (spec.effectKind !== "none") result[spec.effectKind] = (result[spec.effectKind] || 0) + level * spec.perLevel;
      if (spec.secondaryKind !== "none") result[spec.secondaryKind] = (result[spec.secondaryKind] || 0) + level * spec.secondaryPerLevel;
    });
    return result;
  }
  function specialLevel(special) { return localKeys.reduce((total, key) => total + (specs[key].special === special ? state.localLevels[key] : 0), 0); }
  function activeAutoKeys() { return state.permanentLevels.auto_all ? localKeys : state.autoUnlocked; }
  function speedMultiplier() {
    const effects = sumEffects();
    let base = 1 + (effects.speed_add || 0);
    base *= 1 + (effects.depth_efficiency || 0);
    base *= (1 + Math.min(12, state.localLevels.cat || 0)) * (1 + (effects.cat_sync || 0));
    base *= 1 + (effects.carry_add || 0) * .35;
    let permanent = 1 + state.permanentLevels.planetary_power + 1.5 * state.permanentLevels.core_quantum;
    if (state.burstSeconds > 0) permanent *= 100;
    return Math.max(1, base * permanent);
  }
  function available(key) {
    const spec = specs[key];
    if (!spec) return false;
    if (state.permanentLevels.auto_all || state.autoUnlocked.includes(key)) return state.localLevels[key] < spec.max;
    if (progress() + 1e-12 < spec.unlock) return false;
    return spec.prerequisites.every((required) => (state.localLevels[required] || 0) >= 1);
  }
  function canAfford(cost) { return Object.entries(cost).every(([key, value]) => resourceTotal(key) + 1e-9 >= value); }
  function spend(cost) { Object.entries(cost).forEach(([key, value]) => { state.resources[key] = resourceTotal(key) - value; }); }
  function pushEvent(message, tone = "normal") {
    state.events.unshift({ message, tone, at: `D${day()} ${String(Math.floor(minuteOfDay() / 60)).padStart(2, "0")}:${String(minuteOfDay() % 60).padStart(2, "0")}` });
    state.events = state.events.slice(0, 60);
  }
  function buyLocal(key, amount = 1, automatic = false) {
    const spec = specs[key];
    if (!spec || !Number.isInteger(amount) || amount < 1) return false;
    const level = state.localLevels[key] || 0;
    const maxAmount = Math.min(amount, spec.max - level);
    if (!maxAmount || (!automatic && !available(key))) return false;
    const cost = costAt(spec, level, maxAmount);
    if (!canAfford(cost)) return false;
    spend(cost);
    state.localLevels[key] += maxAmount;
    if (!state.everLocalKeys.includes(key)) state.everLocalKeys.push(key);
    if (state.localLevels[key] >= 3 && !state.autoUnlocked.includes(key)) {
      state.autoUnlocked.push(key);
      pushEvent(`${spec.name} 达到 3 级，永久自动采购已解锁`, "good");
    }
    if (!automatic) pushEvent(`购买 ${spec.name} +${maxAmount}`, "upgrade");
    return true;
  }
  function buyCore(key) {
    const spec = CORE_SPECS.find((item) => item.key === key); const level = state.permanentLevels[key] || 0;
    if (!spec || level >= spec.max || state.cores < spec.cost) return false;
    state.cores -= spec.cost; state.permanentLevels[key] += 1;
    pushEvent(`核心科技：${spec.name} Lv.${state.permanentLevels[key]}`, "core");
    return true;
  }
  function autoPurchase() {
    const keys = activeAutoKeys();
    keys.forEach((key) => { if (available(key)) buyLocal(key, 1, true); });
  }
  function oreYield() {
    const p = progress(); const effects = sumEffects();
    const weights = [0.68, 0.25, 0.055, 0.014, 0.001];
    if (p > .12) { weights[0] -= .08; weights[1] += .05; weights[2] += .02; weights[3] += .009; weights[4] += .001; }
    if (p > .58) { weights[0] -= .08; weights[1] -= .02; weights[2] += .04; weights[3] += .04; weights[4] += .02; }
    const rare = Math.min(.4, (effects.rare_find || 0) + specialLevel("ore_echo") * .01);
    weights[0] = Math.max(.1, weights[0] - rare * .5); weights[1] += rare * .24; weights[2] += rare * .16; weights[3] += rare * .08; weights[4] += rare * .02;
    let total = 10 * speedMultiplier() * (1 + (effects.carry_add || 0)) * (1 + (effects.yield_add || 0));
    if (specialLevel("parallel_bore") && Math.random() < Math.min(.25, .01 * specialLevel("parallel_bore"))) total *= 2;
    const noise = Math.max(.7, Math.min(1.3, 1 + (Math.random() - .5) * .12));
    return ORES.map((ore, index) => total * weights[index] * noise);
  }
  function simulateMinute() {
    if (state.depth >= state.targetDepth) prestige();
    const effects = sumEffects(); let gain = 8 * speedMultiplier();
    gain *= 1 + (effects.speed_add || 0) * .02;
    gain *= Math.max(.7, Math.min(1.3, 1 + (Math.random() - .5) * .05));
    if (specialLevel("gravity_sling") && progress() > .25 && progress() < .75) gain *= 1 + .1 * specialLevel("gravity_sling");
    if (specialLevel("time_dilation")) gain *= 1 + .015 * specialLevel("time_dilation");
    if (specialLevel("cat_overclock") && state.localLevels.cat && Math.random() < Math.min(.25, .02 * state.localLevels.cat * specialLevel("cat_overclock"))) gain *= 2;
    if ((effects.crit_chance || 0) && Math.random() < Math.min(.4, effects.crit_chance)) gain *= 1 + Math.max(.2, effects.crit_power || 0);
    state.depth = Math.min(state.targetDepth, state.depth + gain);
    const burstReady = progress() >= SPECIAL_BURST_THRESHOLD;
    if (burstReady && specialLevel("phase_skip") && Math.random() < .001 * specialLevel("phase_skip")) state.depth = Math.min(state.targetDepth, state.depth + state.targetDepth * .0005);
    if (burstReady && specialLevel("quantum_tunnel") && Math.random() < .0002 * specialLevel("quantum_tunnel")) state.depth = Math.min(state.targetDepth, state.depth + state.targetDepth * .001);
    if (specialLevel("singularity_finish") && progress() >= .97) state.depth = Math.min(state.targetDepth, state.depth + state.targetDepth * .01 * specialLevel("singularity_finish"));
    const yields = oreYield(); const refine = .72 + (effects.credit_add || 0); const value = 1 + (effects.ore_value || 0); const salvage = 1 + (effects.salvage || 0);
    yields.forEach((amount, index) => { const ore = ORES[index]; state.resources[ore.key] += amount; state.resources.credits += amount * ore.value * refine * value * salvage; });
    if (specialLevel("vacuum_cache")) state.resources.credits += speedMultiplier() * .5 * specialLevel("vacuum_cache");
    state.totalMinutes += 1;
    state.maxSpeed = Math.max(state.maxSpeed, speedMultiplier());
    if (state.burstSeconds > 0) state.burstSeconds = Math.max(0, state.burstSeconds - 60);
    // 固定步进测试每 10 分钟结算一次自动采购；玩家的小时决策不阻塞后台成长。
    if (state.totalMinutes % 10 === 0) autoPurchase();
    if (state.depth >= state.targetDepth) prestige();
  }
  function simulateMinutes(minutes) {
    const count = Math.max(0, Math.floor(minutes));
    for (let index = 0; index < count; index += 1) simulateMinute();
    queueSave(); render();
  }
  function prestige() {
    const survey = state.permanentLevels.core_survey || 0; const resonance = specialLevel("core_resonance");
    const relativityActive = specialLevel("relativity_burst") > 0;
    const extra = Math.floor((state.permanentLevels.entanglement || 0) * .25); const destroyed = 1 + extra;
    state.planets += destroyed; state.cores += 1 + survey + resonance; state.resetDays.push(day());
    state.depth = 0; state.resources = { credits: 0, tin: 0, copper: 0, quartz: 0, gold: 0, coreshard: 0 };
    localKeys.forEach((key) => { state.localLevels[key] = 0; }); state.burstSeconds = relativityActive ? 60 : 0;
    pushEvent(`星球爆裂：摧毁 ${destroyed} 颗，获得 ${1 + survey + resonance} 核心`, "core");
  }

  function renderResources() {
    const list = [{ key: "credits", name: "矿币", icon: "¢", color: "credits" }, ...ORES];
    els.resourceStrip.innerHTML = list.map((item) => `<div class="resource-chip ${item.color}"><span class="resource-name"><i class="resource-icon">${item.icon}</i>${item.name}</span><strong class="resource-value">${formatNumber(resourceTotal(item.key), 1)}</strong></div>`).join("");
  }
  function renderOverview() {
    const p = progress(); const era = currentEra(); const speed = speedMultiplier();
    els.runState.textContent = state.running ? "自动挖掘中" : "暂停中"; els.eraName.textContent = era.name;
    els.depthValue.textContent = formatNumber(state.depth, 2); els.targetDepth.textContent = formatNumber(state.targetDepth, 0);
    els.depthProgress.style.width = `${p * 100}%`; els.progressLabel.textContent = formatPercent(p); els.speedLabel.textContent = `推进 ×${formatNumber(speed, 2)} · D${day()} ${String(Math.floor(minuteOfDay() / 60)).padStart(2, "0")}:${String(minuteOfDay() % 60).padStart(2, "0")}`;
    els.planetCount.textContent = formatNumber(state.planets, 0); els.coreCount.textContent = formatNumber(state.cores, 0); els.coreValue.textContent = formatNumber(state.cores, 0);
    els.runBtn.classList.toggle("running", state.running); els.runIcon.textContent = state.running ? "Ⅱ" : "▶"; els.runText.textContent = state.running ? "暂停自动挖矿" : "开始自动挖矿";
    const beamScale = .3 + Math.min(.7, p); els.drillBeam.setAttribute("transform", `rotate(${(p * 35).toFixed(1)} 126 101) scale(${beamScale.toFixed(3)})`);
  }
  function renderEraTabs() {
    els.eraTabs.innerHTML = ERA_LIST.map((era) => {
      const unlocked = progress() >= era.unlock || state.everLocalKeys.some((key) => specs[key].era === era.key);
      return `<button class="era-tab ${state.selectedEra === era.key ? "active" : ""}" data-era="${era.key}" type="button" ${unlocked ? "" : "disabled"}>${era.short}<small>${unlocked ? "" : "锁"}</small></button>`;
    }).join("");
  }
  function renderTech() {
    const activeEra = state.selectedEra; const search = (els.techSearch.value || "").trim().toLowerCase();
    const keys = localKeys.filter((key) => specs[key].era === activeEra && (!search || specs[key].name.toLowerCase().includes(search)));
    const reached = state.everLocalKeys.length; const specialReached = state.everLocalKeys.filter((key) => specs[key].special).length;
    els.techCount.textContent = `${reached} / ${localKeys.length}`; els.techSummary.innerHTML = `<span>${ERA_LIST.find((era) => era.key === activeEra)?.name || "科技"} · ${keys.length} 个节点</span><span>特殊 ${specialReached}/29 · 自动 ${state.autoUnlocked.length}/${localKeys.length}</span>`;
    if (!keys.length) { els.techList.innerHTML = `<div class="empty-state">没有匹配的科技节点</div>`; return; }
    els.techList.innerHTML = keys.map((key) => techCard(key)).join("");
  }
  function techCard(key) {
    const spec = specs[key]; const level = state.localLevels[key] || 0; const isAvailable = available(key); const maxed = level >= spec.max; const special = spec.special ? `<span class="special-tag">${SPECIAL_NAMES[spec.special] || "特殊"}</span>` : "";
    const status = maxed ? "max" : !isAvailable ? "locked" : ""; const cost = costAt(spec, level, 1);
    const lockText = !isAvailable && progress() < spec.unlock ? `深度 ${formatPercent(spec.unlock)} 解锁` : !isAvailable ? "需要前置科技" : costText(cost);
    return `<article class="tech-card"><div class="tech-card-head"><div><div class="tech-name">${spec.name}</div>${special}</div><span class="tech-level ${status}">${maxed ? "MAX" : `Lv.${level}/${spec.max}`}</span></div><p class="tech-effect">${spec.effect}</p><div class="tech-foot"><span class="tech-cost">${isAvailable && !maxed ? `<b>${lockText}</b>` : lockText}</span><span class="tech-actions"><button class="buy-btn" data-buy="${key}" data-amount="1" type="button" ${!isAvailable || maxed ? "disabled" : ""}>+1</button><button class="buy-btn" data-buy="${key}" data-amount="3" type="button" ${!isAvailable || maxed ? "disabled" : ""}>+3</button></span></div></article>`;
  }
  function renderCore() {
    els.coreList.innerHTML = CORE_SPECS.map((spec) => { const level = state.permanentLevels[spec.key] || 0; const disabled = level >= spec.max || state.cores < spec.cost; return `<div class="core-item"><div><div class="core-item-name">${spec.name} <span class="core-item-level">Lv.${level}/${spec.max}</span></div><div class="core-item-effect">${spec.effect}</div><button class="core-buy" data-core="${spec.key}" type="button" ${disabled ? "disabled" : ""}>消耗 ${spec.cost} 核心升级</button></div></div>`; }).join("");
  }
  function renderEvents() { els.eventLog.innerHTML = state.events.length ? state.events.map((event) => `<div class="event ${event.tone}"><strong>${event.at}</strong> · ${event.message}</div>`).join("") : `<div class="event empty">等待第一次挖掘结算</div>`; }
  function render() {
    if (renderQueued) return; renderQueued = true;
    requestAnimationFrame(() => { renderQueued = false; renderOverview(); renderResources(); renderEraTabs(); renderTech(); renderCore(); renderEvents(); });
  }
  function toast(message) { els.toast.textContent = message; els.toast.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => els.toast.classList.remove("show"), 2200); }
  function queueSave() { clearTimeout(saveTimer); saveTimer = setTimeout(() => saveState(false), 350); }
  function saveState(manual = true) { localStorage.setItem(SAVE_KEY, JSON.stringify({ ...state, savedAt: new Date().toISOString(), running: false })); els.cacheState.innerHTML = "<i></i>缓存已写入"; els.saveMeta.textContent = `最近保存：${new Date().toLocaleString()}`; if (manual) toast("存档已保存到浏览器缓存"); }
  function loadState(manual = true) {
    const raw = localStorage.getItem(SAVE_KEY); if (!raw) { if (manual) toast("没有找到浏览器存档"); return false; }
    try { const incoming = JSON.parse(raw); const fresh = newState(); state = Object.assign(fresh, incoming, { running: false }); state.localLevels = Object.assign(fresh.localLevels, incoming.localLevels || {}); state.permanentLevels = Object.assign(fresh.permanentLevels, incoming.permanentLevels || {}); state.resources = Object.assign(fresh.resources, incoming.resources || {}); render(); if (manual) toast("存档已读取"); return true; } catch (error) { if (manual) toast("存档格式无法读取"); return false; }
  }
  function resetState() { if (!window.confirm("确定清除浏览器存档并重置原型吗？")) return; stopRunning(); state = newState(); localStorage.removeItem(SAVE_KEY); els.saveMeta.textContent = "本地缓存尚未写入"; pushEvent("新的矿工档案已建立", "good"); render(); toast("已重置测试档案"); }
  function stopRunning() { state.running = false; if (window.runTimer) { clearInterval(window.runTimer); window.runTimer = null; } render(); }
  function toggleRunning() {
    state.running = !state.running;
    if (state.running) { window.runTimer = setInterval(() => simulateMinutes(state.speedChoice), 500); toast(`自动挖矿 ×${state.speedChoice}`); } else { clearInterval(window.runTimer); window.runTimer = null; toast("自动挖矿已暂停"); }
    render();
  }
  function cheat(type) {
    if (type === "hour") simulateMinutes(60);
    if (type === "day") simulateMinutes(1440 - minuteOfDay());
    if (type === "week") simulateMinutes(10080);
    if (type === "depth") { state.depth = state.targetDepth * .5; pushEvent("测试：深度跳至 50%", "core"); render(); queueSave(); }
    if (type === "planet") { state.depth = state.targetDepth; simulateMinutes(1); toast("测试：已触发爆星"); }
    if (type === "resources") { Object.keys(state.resources).forEach((key) => { state.resources[key] = key === "credits" ? 1e12 : 1e9; }); pushEvent("测试：资源已补满", "core"); render(); queueSave(); }
    if (type === "cores") { state.cores += 100; pushEvent("测试：获得 100 核心", "core"); render(); queueSave(); }
    if (type === "tech") { localKeys.forEach((key) => { state.localLevels[key] = 3; if (!state.everLocalKeys.includes(key)) state.everLocalKeys.push(key); if (!state.autoUnlocked.includes(key)) state.autoUnlocked.push(key); }); pushEvent("测试：全部本地科技达到 3 级", "core"); render(); queueSave(); }
  }
  function exportSave() { const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `s2-vnext-d${day()}.json`; anchor.click(); URL.revokeObjectURL(url); toast("JSON 存档已导出"); }
  function importSave(file) { const reader = new FileReader(); reader.onload = () => { try { const incoming = JSON.parse(reader.result); const fresh = newState(); state = Object.assign(fresh, incoming, { running: false }); state.localLevels = Object.assign(fresh.localLevels, incoming.localLevels || {}); state.permanentLevels = Object.assign(fresh.permanentLevels, incoming.permanentLevels || {}); state.resources = Object.assign(fresh.resources, incoming.resources || {}); saveState(false); render(); toast("JSON 存档已导入"); } catch (error) { toast("JSON 文件无法导入"); } }; reader.readAsText(file); }

  els.runBtn.addEventListener("click", toggleRunning);
  $("tickBtn").addEventListener("click", () => cheat("hour"));
  $("dayBtn").addEventListener("click", () => cheat("day"));
  $("saveBtn").addEventListener("click", () => saveState(true));
  $("loadBtn").addEventListener("click", () => loadState(true));
  $("resetBtn").addEventListener("click", resetState);
  $("clearLogBtn").addEventListener("click", () => { state.events = []; render(); });
  $("exportBtn").addEventListener("click", exportSave);
  $("importInput").addEventListener("change", (event) => { if (event.target.files[0]) importSave(event.target.files[0]); event.target.value = ""; });
  els.techSearch.addEventListener("input", renderTech);
  els.eraTabs.addEventListener("click", (event) => { const button = event.target.closest("[data-era]"); if (button && !button.disabled) { state.selectedEra = button.dataset.era; renderTech(); renderEraTabs(); } });
  els.techList.addEventListener("click", (event) => { const button = event.target.closest("[data-buy]"); if (!button) return; if (buyLocal(button.dataset.buy, Number(button.dataset.amount))) { queueSave(); render(); } else toast("资源不足或尚未达到解锁条件"); });
  els.coreList.addEventListener("click", (event) => { const button = event.target.closest("[data-core]"); if (!button) return; if (buyCore(button.dataset.core)) { queueSave(); render(); } else toast("核心不足或已达到上限"); });
  document.querySelectorAll("[data-speed]").forEach((button) => button.addEventListener("click", () => { state.speedChoice = Number(button.dataset.speed); document.querySelectorAll("[data-speed]").forEach((item) => item.classList.toggle("active", item === button)); render(); }));
  document.querySelectorAll("[data-cheat]").forEach((button) => button.addEventListener("click", () => cheat(button.dataset.cheat)));

  if (!loadState(false)) { pushEvent("新的矿工档案已建立", "good"); }
  render();
})();
