/**
 * S2 星穹矿脉 v5 — 多系统升级 + 指数加速
 *
 * 五条升级线（局内）：钻头(8) + 矿物等级(25) + 引擎(6) + 自动化(5) + 地层科技(5) = 49项
 * 永久升级（跨局）：起步倍率(9) + 全局加速(6) + 自动化保留(5) + 星核倍增(2) = 22项
 *
 * 深度公式: depth/pulse = Σ(产量×权重) × 钻头倍率 × 引擎倍率 × 全局倍率 × depthScale / pulses
 * 二阶：每轮永久升级使下一轮指数级加速，稳定态后批量外推至 10^308
 */
(function () {
  "use strict";

  // ════════════ 配置 ════════════
  var CFG = {
    core: 1e8,          // 地心深度
    pulses: 4,          // 每日结算波次
    daySeconds: 12,     // 1游戏日 = 12秒（×1速）
    secondExponent: 308, // 二阶门槛 10^308
    depthScale: 2000,   // 深度转换系数（V4的1/100）
    mineralNoise: 0.02,  // 扰动幅度 ±2%
    exactCycleLimit: 64  // 精确模拟硬上限
  };
  var SECOND_NEED = 10n ** BigInt(CFG.secondExponent);

  // ════════════ 数据定义 ════════════

  // 矿物（基础产量降低到V4的1/9~1/9）
  var ORES = [
    { key: "stone", name: "猫砂石", rarity: "N", layer: "风化壳", unlock: 0, base: 1.0, cost: 8, cg: 1.74, pg: 2.04, weight: 1.0, color: "#64748b" },
    { key: "copper", name: "铜须矿", rarity: "R", layer: "浅岩层", unlock: 0.12, base: 0.35, cost: 24, cg: 1.76, pg: 2.08, weight: 2.2, color: "#2563eb" },
    { key: "amethyst", name: "紫晶猫眼", rarity: "SR", layer: "晶簇层", unlock: 0.32, base: 0.12, cost: 90, cg: 1.78, pg: 2.12, weight: 5.0, color: "#7c3aed" },
    { key: "gold", name: "金猫锭", rarity: "SSR", layer: "熔金层", unlock: 0.58, base: 0.04, cost: 360, cg: 1.80, pg: 2.16, weight: 12.0, color: "#b45309" },
    { key: "rainbow", name: "虹核晶", rarity: "UR", layer: "星核层", unlock: 0.82, base: 0.01, cost: 1800, cg: 1.82, pg: 2.20, weight: 30.0, color: "#dc2626" }
  ];

  // 钻头系统（8级，每级×2，总×256）
  var DRILLS = [
    { name: "铁爪钻头", unlock: 0, cost: { stone: 8 } },
    { name: "钢芯钻头", unlock: 0.03, cost: { stone: 40 } },
    { name: "合金钻头", unlock: 0.12, cost: { copper: 20 } },
    { name: "等离子钻头", unlock: 0.25, cost: { copper: 80 } },
    { name: "量子钻头", unlock: 0.40, cost: { amethyst: 30 } },
    { name: "反物质钻头", unlock: 0.55, cost: { amethyst: 120 } },
    { name: "中子钻头", unlock: 0.70, cost: { gold: 40 } },
    { name: "奇点钻头", unlock: 0.85, cost: { gold: 160 } }
  ];

  // 深度引擎（6级，每级×1.3，总×4.83）
  var ENGINES = [
    { name: "基础推进器", unlock: 0.05, cost: { stone: 50 } },
    { name: "强化推进器", unlock: 0.15, cost: { stone: 100, copper: 30 } },
    { name: "脉冲推进器", unlock: 0.28, cost: { stone: 200, copper: 60 } },
    { name: "裂隙推进器", unlock: 0.42, cost: { amethyst: 40, copper: 100 } },
    { name: "量子隧穿器", unlock: 0.60, cost: { amethyst: 80, copper: 150 } },
    { name: "维度折叠器", unlock: 0.78, cost: { amethyst: 160, gold: 50 } }
  ];

  // 自动化模块（5级，局内按深度解锁）
  var AUTOS = [
    { key: "drill", name: "自动钻头维护", unlock: 0.08, cost: { stone: 100 }, text: "自动购买钻头升级" },
    { key: "mineral", name: "自动矿物处理", unlock: 0.18, cost: { copper: 50 }, text: "自动购买矿物等级" },
    { key: "engine", name: "自动深度推进", unlock: 0.35, cost: { amethyst: 80 }, text: "自动购买深度引擎" },
    { key: "layer", name: "自动地层勘探", unlock: 0.50, cost: { gold: 60 }, text: "自动确认新地层" },
    { key: "fullauto", name: "全自动采矿", unlock: 0.90, cost: { rainbow: 200 }, text: "自动执行一阶无限" }
  ];

  // auto key → perm key 映射
  var AUTO_PERM_MAP = {
    drill: "autoDrill", mineral: "autoMineral", engine: "autoEngine",
    layer: "autoLayer", fullauto: "autoFull"
  };

  // 地层科技（5项，特色加成）
  var LAYER_TECHS = [
    { key: "stone_tech", name: "猫砂石专精", unlock: 0.05, cost: { stone: 30 }, text: "猫砂石产量 ×3", oreIdx: 0 },
    { key: "copper_tech", name: "铜矿感应", unlock: 0.12, cost: { stone: 50 }, text: "铜须矿发现时自带 Lv.2", oreIdx: 1 },
    { key: "crystal_tech", name: "晶体共振", unlock: 0.32, cost: { amethyst: 40 }, text: "全矿产量 ×1.5", oreIdx: -1 },
    { key: "gold_tech", name: "熔岩护盾", unlock: 0.58, cost: { gold: 60 }, text: "金猫锭发现时自带 Lv.2", oreIdx: 3 },
    { key: "rainbow_tech", name: "星核共鸣", unlock: 0.82, cost: { rainbow: 100 }, text: "虹核晶产量 ×5", oreIdx: 4 }
  ];

  // 永久升级（22项，星核购买）
  var PERMS = [
    // 起步倍率（9项）
    { key: "drill1", name: "钻头继承 I", cost: 1, text: "开局自带钻头 Lv.2", cat: "起步" },
    { key: "drill2", name: "钻头继承 II", cost: 2, text: "开局自带钻头 Lv.4", cat: "起步" },
    { key: "drill3", name: "钻头继承 III", cost: 3, text: "开局自带钻头 Lv.6", cat: "起步" },
    { key: "ore1", name: "矿物继承 I", cost: 1, text: "开局全矿 Lv.1", cat: "起步" },
    { key: "ore2", name: "矿物继承 II", cost: 2, text: "开局全矿 Lv.2", cat: "起步" },
    { key: "ore3", name: "矿物继承 III", cost: 3, text: "开局全矿 Lv.3", cat: "起步" },
    { key: "reson1", name: "矿物共振 I", cost: 2, text: "开局全矿额外 Lv.+1", cat: "起步" },
    { key: "reson2", name: "矿物共振 II", cost: 4, text: "开局全矿额外 Lv.+1", cat: "起步" },
    { key: "reson3", name: "矿物共振 III", cost: 6, text: "开局全矿额外 Lv.+1", cat: "起步" },
    // 全局加速（6项）
    { key: "global1", name: "全局加速 I", cost: 2, text: "全局深度效率 ×1.5", cat: "加速" },
    { key: "global2", name: "全局加速 II", cost: 4, text: "全局深度效率 ×1.5", cat: "加速" },
    { key: "global3", name: "全局加速 III", cost: 6, text: "全局深度效率 ×1.5", cat: "加速" },
    { key: "compress1", name: "深度压缩 I", cost: 2, text: "地心深度需求 −20%", cat: "加速" },
    { key: "compress2", name: "深度压缩 II", cost: 4, text: "地心深度需求 −20%", cat: "加速" },
    { key: "compress3", name: "深度压缩 III", cost: 6, text: "地心深度需求 −20%", cat: "加速" },
    // 自动化保留（5项）
    { key: "autoDrill", name: "自动钻头模块", cost: 1, text: "开局自带自动钻头", cat: "自动" },
    { key: "autoMineral", name: "自动处理模块", cost: 2, text: "开局自带自动矿物处理", cat: "自动" },
    { key: "autoEngine", name: "自动引擎模块", cost: 3, text: "开局自带自动深度推进", cat: "自动" },
    { key: "autoLayer", name: "自动勘探模块", cost: 4, text: "开局自带自动地层勘探", cat: "自动" },
    { key: "autoFull", name: "全自动模块", cost: 5, text: "开局自带全自动采矿", cat: "自动" },
    // 星核倍增（2项）
    { key: "shard1", name: "星核倍增 I", cost: 3, text: "每次获得 2 星核", cat: "星核" },
    { key: "shard2", name: "星核倍增 II", cost: 6, text: "每次获得 3 星核", cat: "星核" }
  ];

  var TAB_NAMES = {
    drill: "钻头系统", ore: "矿物等级", engine: "深度引擎",
    auto: "自动化模块", layer: "地层科技", perm: "永久升级"
  };

  // ════════════ 状态 ════════════
  function fresh() {
    return {
      day: 1, dayProgress: 0, mining: false, depth: 0,
      resets: 0, shards: 0, spent: 0, perm: {},
      drillLv: 0, engineLv: 0, auto: {}, layerTech: {},
      lv: [0, 0, 0, 0, 0], stock: [0, 0, 0, 0, 0],
      open: [true, false, false, false, false],
      manual: 0, cycleDay: 1, pulseIndex: 0,
      logs: [], won: false, extrapolation: null,
      activeTab: "drill"
    };
  }

  var st = fresh(), speed = 1, acc = 0, last = performance.now(), toastTimer = 0;

  // ════════════ 辅助函数 ════════════
  function id(x) { return document.getElementById(x); }
  function fmt(x) {
    if (x < 1e6) return Math.floor(x).toLocaleString("zh-CN");
    return x.toExponential(2);
  }
  function has(k) { return !!st.perm[k]; }
  function hasAuto(k) { return st.auto[k] || st.perm[AUTO_PERM_MAP[k]]; }
  function log(s, c) { st.logs.unshift({ s: s, c: c || "" }); st.logs = st.logs.slice(0, 80); }
  function toast(s) {
    id("toast").textContent = s;
    id("toast").classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { id("toast").classList.remove("show"); }, 1400);
  }

  // ════════════ 倍率计算 ════════════
  function drillMult() { return Math.pow(2, st.drillLv); }
  function engineMult() { return Math.pow(1.3, st.engineLv); }
  function globalMult() {
    var m = 1;
    if (has("global1")) m *= 1.5;
    if (has("global2")) m *= 1.5;
    if (has("global3")) m *= 1.5;
    return m;
  }
  function layerMult(oreIdx) {
    var m = 1;
    if (st.layerTech["crystal_tech"]) m *= 1.5;
    if (oreIdx === 0 && st.layerTech["stone_tech"]) m *= 3;
    if (oreIdx === 4 && st.layerTech["rainbow_tech"]) m *= 5;
    return m;
  }
  function totalMult() { return drillMult() * engineMult() * globalMult(); }

  // 深度压缩：减少地心目标深度
  function effectiveCore() {
    var c = CFG.core;
    if (has("compress1")) c *= 0.8;
    if (has("compress2")) c *= 0.8;
    if (has("compress3")) c *= 0.8;
    return c;
  }

  // 指数增长倍率：基于永久升级计算下一轮的起步速度倍率
  function growthRate() {
    // 预期钻头等级（来自永久升级）
    var nextDrillLv = 0;
    if (has("drill1")) nextDrillLv = 2;
    if (has("drill2")) nextDrillLv = 4;
    if (has("drill3")) nextDrillLv = 6;
    // 预期矿物等级加成（继承+共振）
    var oreBonus = 0;
    if (has("ore1")) oreBonus = 1;
    if (has("ore2")) oreBonus = 2;
    if (has("ore3")) oreBonus = 3;
    if (has("reson1")) oreBonus += 1;
    if (has("reson2")) oreBonus += 1;
    if (has("reson3")) oreBonus += 1;
    oreBonus = Math.min(5, oreBonus);
    // 矿物产量倍率（以猫砂石为基准）
    var oreMult = Math.pow(ORES[0].pg, oreBonus);
    // 钻头倍率
    var drillM = Math.pow(2, nextDrillLv);
    // 全局倍率
    var gMult = globalMult();
    // 深度压缩等效加速
    var coreRatio = CFG.core / effectiveCore();
    return drillM * oreMult * gMult * coreRatio;
  }

  // ════════════ 成本处理 ════════════
  function oreCost(i) { return ORES[i].cost * Math.pow(ORES[i].cg, st.lv[i]); }

  function oreKeyToIdx(key) {
    for (var i = 0; i < ORES.length; i++) if (ORES[i].key === key) return i;
    return -1;
  }

  function canAfford(cost) {
    for (var k in cost) {
      var idx = oreKeyToIdx(k);
      if (idx < 0 || st.stock[idx] < cost[k]) return false;
    }
    return true;
  }

  function spendCost(cost) {
    for (var k in cost) {
      var idx = oreKeyToIdx(k);
      if (idx >= 0) st.stock[idx] -= cost[k];
    }
  }

  function costText(cost) {
    return Object.keys(cost).map(function (k) {
      var ore = ORES.find(function (o) { return o.key === k; });
      return fmt(cost[k]) + " " + (ore ? ore.name : k);
    }).join(" + ");
  }

  // ════════════ 扰动 ════════════
  function disturbance(ore, pulse) {
    return 1 + CFG.mineralNoise * [-1, 0.5, 1, -0.5][(ore + pulse) % 4];
  }

  function projectStable(prefix, sample, count) {
    return {
      resets: prefix.resets + count,
      days: prefix.days + BigInt(sample.days) * count,
      reward: prefix.reward + BigInt(sample.reward) * count
    };
  }

  // ════════════ 升级购买 ════════════
  function tryBuyOreLevel(i, auto) {
    if (!st.open[i] || st.lv[i] >= 25) return false;
    if (st.stock[i] < oreCost(i)) return false;
    st.stock[i] -= oreCost(i);
    st.lv[i]++;
    if (!auto) { st.manual++; log(ORES[i].name + " 升级 → Lv." + st.lv[i], "up"); }
    return true;
  }

  function tryBuyDrill(auto) {
    if (st.drillLv >= 8) return false;
    var d = DRILLS[st.drillLv];
    if (st.depth / effectiveCore() < d.unlock) return false;
    if (!canAfford(d.cost)) return false;
    spendCost(d.cost);
    st.drillLv++;
    if (!auto) { st.manual++; log("钻头升级 → Lv." + st.drillLv + " " + d.name + "（×" + drillMult().toFixed(0) + "）", "up"); }
    else log("自动钻头 → Lv." + st.drillLv + " " + d.name, "up");
    return true;
  }

  function tryBuyEngine(auto) {
    if (st.engineLv >= 6) return false;
    var e = ENGINES[st.engineLv];
    if (st.depth / effectiveCore() < e.unlock) return false;
    if (!canAfford(e.cost)) return false;
    spendCost(e.cost);
    st.engineLv++;
    if (!auto) { st.manual++; log("引擎升级 → Lv." + st.engineLv + " " + e.name + "（×" + engineMult().toFixed(2) + "）", "up"); }
    else log("自动引擎 → Lv." + st.engineLv + " " + e.name, "up");
    return true;
  }

  function tryBuyAuto(idx) {
    var a = AUTOS[idx];
    if (st.auto[a.key]) return false;
    if (st.depth / effectiveCore() < a.unlock) return false;
    if (!canAfford(a.cost)) return false;
    spendCost(a.cost);
    st.auto[a.key] = true;
    st.manual++;
    log("自动化解锁：" + a.name + " — " + a.text, "win");
    toast(a.name + " 已激活");
    return true;
  }

  function tryBuyLayerTech(idx) {
    var t = LAYER_TECHS[idx];
    if (st.layerTech[t.key]) return false;
    if (st.depth / effectiveCore() < t.unlock) return false;
    if (!canAfford(t.cost)) return false;
    spendCost(t.cost);
    st.layerTech[t.key] = true;
    st.manual++;
    // 即时应用效果
    if (t.key === "copper_tech" && st.open[1]) st.lv[1] = Math.max(st.lv[1], 2);
    if (t.key === "gold_tech" && st.open[3]) st.lv[3] = Math.max(st.lv[3], 2);
    log("地层科技：" + t.name + " — " + t.text, "win");
    toast(t.name);
    return true;
  }

  function tryBuyPerm(key) {
    var p = PERMS.find(function (x) { return x.key === key; });
    if (!p || has(key)) return false;
    if (st.shards < p.cost) return false;
    st.shards -= p.cost;
    st.spent += p.cost;
    st.perm[key] = true;
    log("永久升级：" + p.name + " — " + p.text, "win");
    toast(p.name + " 已永久生效");
    return true;
  }

  // ════════════ 自动化 ════════════
  function runAutomation() {
    if (hasAuto("drill")) tryBuyDrill(true);
    if (hasAuto("mineral")) ORES.forEach(function (_, i) { tryBuyOreLevel(i, true); });
    if (hasAuto("engine")) tryBuyEngine(true);
  }

  // ════════════ 地层发现 ════════════
  function discover() {
    var r = st.depth / effectiveCore();
    ORES.forEach(function (o, i) {
      if (!st.open[i] && r >= o.unlock) {
        st.open[i] = true;
        // 地层科技即时效果
        if (i === 1 && st.layerTech["copper_tech"]) st.lv[1] = 2;
        if (i === 3 && st.layerTech["gold_tech"]) st.lv[3] = 2;
        if (hasAuto("layer")) {
          log("自动确认 " + o.layer + " · " + o.name, "inf");
        } else {
          st.manual++;
          log("发现 " + o.layer + " · " + o.name, "inf");
        }
      }
    });
  }

  // ════════════ 挖矿脉冲 ════════════
  function pulse() {
    if (!st.mining || st.won) return;
    var mineralGain = 0;
    ORES.forEach(function (o, i) {
      if (st.open[i]) {
        var prod = o.base * Math.pow(o.pg, st.lv[i]) * layerMult(i);
        var expected = prod / CFG.pulses;
        var q = expected * disturbance(i, st.pulseIndex);
        st.stock[i] += q;
        mineralGain += q * o.weight;
      }
    });
    st.pulseIndex++;
    var depthGain = mineralGain * drillMult() * engineMult() * globalMult() * CFG.depthScale;
    st.depth += depthGain;
    discover();
    runAutomation();
    if (st.depth >= effectiveCore()) firstOrder();
  }

  // ════════════ 一阶无限 ════════════
  function firstOrder() {
    if (!hasAuto("fullauto")) {
      st.manual++;
      st.mining = false;
      log("已挖穿星球：请手动执行一阶无限", "win");
      toast("等待一阶无限");
      return;
    }
    doReset();
  }

  function doReset() {
    if (st.depth < effectiveCore()) return false;
    st.resets++;
    var reward = 1;
    if (has("shard1")) reward = 2;
    if (has("shard2")) reward = 3;
    st.shards += reward;
    log("一阶无限 #" + st.resets + "：库存、等级、钻头、引擎、自动化、地层科技全部清除；获得 " + reward + " 星核", "inf");

    // 检查是否全部永久升级已购买
    var allPerms = PERMS.every(function (p) { return has(p.key); });
    if (allPerms) {
      var sampleDays = st.cycleDay;
      var prefix = { resets: BigInt(st.resets), days: BigInt(st.day), reward: BigInt(st.shards) };
      var remaining = SECOND_NEED - prefix.resets;
      var projected = projectStable(prefix, { days: sampleDays, reward: reward }, remaining);
      st.extrapolation = { sampleDays: sampleDays, cycles: remaining, totalDays: projected.days, totalReward: projected.reward };
      st.won = true;
      st.mining = false;
      id("winText").textContent = "已精确模拟 " + st.resets + " 轮；稳定态单循环耗时 " + sampleDays + " 日。其余 " + remaining.toString() + " 轮已按单循环批量外推。";
      id("winModal").classList.add("show");
      return true;
    }
    beginCycle();
    st.mining = true; // 自动开始下一轮
    return true;
  }

  function beginCycle() {
    st.depth = 0;
    st.drillLv = 0;
    st.engineLv = 0;
    st.auto = {};
    st.layerTech = {};
    st.lv = [0, 0, 0, 0, 0];
    st.stock = [0, 0, 0, 0, 0];
    st.open = [true, false, false, false, false];
    st.cycleDay = 1;
    st.pulseIndex = 0;
    st.manual = 0;

    // 永久升级：钻头继承
    if (has("drill1")) st.drillLv = 2;
    if (has("drill2")) st.drillLv = 4;
    if (has("drill3")) st.drillLv = 6;

    // 永久升级：矿物继承
    if (has("ore1")) st.lv = [1, 1, 1, 1, 1];
    if (has("ore2")) st.lv = [2, 2, 2, 2, 2];
    if (has("ore3")) st.lv = [3, 3, 3, 3, 3];

    // 永久升级：矿物共振（在继承基础上额外+1 per level）
    if (has("reson1")) st.lv = st.lv.map(function (v) { return v + 1; });
    if (has("reson2")) st.lv = st.lv.map(function (v) { return v + 1; });
    if (has("reson3")) st.lv = st.lv.map(function (v) { return v + 1; });
    // 封顶 Lv.25
    st.lv = st.lv.map(function (v) { return Math.min(25, v); });

    // 永久升级：自动化保留
    if (has("autoDrill")) st.auto["drill"] = true;
    if (has("autoMineral")) st.auto["mineral"] = true;
    if (has("autoEngine")) st.auto["engine"] = true;
    if (has("autoLayer")) st.auto["layer"] = true;
    if (has("autoFull")) st.auto["fullauto"] = true;

    if (st.drillLv > 0 || Object.keys(st.perm).length > 0) {
      log("新矿区开始（钻头 Lv." + st.drillLv + " · 矿物 Lv." + st.lv[0] + "）", "up");
    } else {
      st.manual++;
      log("新矿区开始（手动整备）", "up");
    }
  }

  // ════════════ 时间推进 ════════════
  function advance(days) {
    var p = days * CFG.pulses + acc;
    var n = Math.floor(p);
    acc = p - n;
    for (var i = 0; i < n; i++) pulse();
    st.dayProgress += days;
    while (st.dayProgress >= 1 && !st.won) {
      st.dayProgress--;
      st.day++;
      st.cycleDay++;
    }
  }

  function currentLayer() {
    var r = st.depth / effectiveCore();
    var x = ORES[0];
    ORES.forEach(function (o) { if (r >= o.unlock) x = o; });
    return x.layer;
  }

  // ════════════ 渲染 ════════════
  function render() {
    var ec = effectiveCore();
    var r = Math.min(1, st.depth / ec);
    var p = st.won ? 1 : 0;
    var permCount = Object.keys(st.perm).length;
    var remaining = PERMS.length - permCount;

    id("coinsVal").textContent = st.shards + " 星核";
    id("depthVal").textContent = fmt(st.depth) + " / " + fmt(ec);
    id("depthBar").style.width = (r * 100) + "%";
    id("depthBarLabel").textContent = (r * 100).toFixed(2) + "% · " + currentLayer();
    id("dayBar").style.width = (st.dayProgress * 100) + "%";
    id("dayBarLabel").textContent = "D" + st.day + " · 本轮 D" + st.cycleDay;

    id("qtyVal").textContent = st.open.filter(Boolean).length + " / 5";
    id("dptVal").textContent = "Lv." + st.drillLv + " · ×" + drillMult().toFixed(0);
    id("engineVal").textContent = "Lv." + st.engineLv + " · ×" + engineMult().toFixed(2);
    id("progressVal").textContent = "挖掘力 ×" + totalMult().toFixed(1);
    id("inf1Val").textContent = (p * 100).toFixed(1) + "%";
    id("ticksVal").textContent = st.won ? "10^308 / 10^308" : st.resets + " / 10^308";
    id("sessionLabel").textContent = st.won ? "已通关" : st.mining ? "挖矿中" : st.depth >= effectiveCore() ? "等待一阶无限" : "已停工";
    id("runPill").textContent = st.mining ? "挖矿中" : "空闲";
    id("dayPill").textContent = "D" + st.day;
    id("infPill").textContent = "二阶 " + (p * 100).toFixed(1) + "%";
    id("upPill").textContent = "本轮手动 " + st.manual;
    id("autoPill").textContent = "永久 " + permCount + "/" + PERMS.length;
    id("settleMode").textContent = "一阶无限 #" + st.resets;
    id("speedLabel").textContent = "1日≈" + (CFG.daySeconds / speed).toFixed(1) + "s · ×" + speed;

    // Stage 2 进度
    if (st.resets > 0) {
      var card = id("stage2Card");
      if (card) card.style.display = "";
      var s2planets = id("s2planets");
      var s2speed = id("s2speed");
      var s2shards = id("s2shards");
      var s2remaining = id("s2remaining");
      if (s2planets) s2planets.textContent = st.resets;
      if (s2speed) s2speed.textContent = "×" + growthRate().toFixed(1);
      if (s2shards) s2shards.textContent = st.spent + " / " + (st.shards + st.spent);
      if (s2remaining) s2remaining.textContent = remaining;
    }

    id("btnStart").disabled = st.mining || st.won || st.depth >= effectiveCore();
    id("btnStop").disabled = !st.mining;
    id("btnDay").textContent = st.depth >= effectiveCore() && !hasAuto("fullauto") ? "一阶无限" : "次日";

    renderUpgradePanel();

    // 矿物库存
    id("oreGrid").innerHTML = ORES.map(function (o, i) {
      return '<div class="ore"><div class="name" style="color:' + o.color + '">' + o.rarity + " " + o.name +
        '</div><div class="qty">' + (st.open[i] ? fmt(st.stock[i]) + " · Lv." + st.lv[i] : "未发现") + "</div></div>";
    }).join("");

    // 五矿成长
    id("rarityBars").innerHTML = ORES.map(function (o, i) {
      return '<div class="rb"><div class="rb-name" style="color:' + o.color + '">' + o.rarity +
        '</div><div class="track"><i style="width:' + Math.min(100, st.lv[i] * 4) + "%;background:" + o.color +
        '"></i></div><div class="rb-pct">Lv.' + st.lv[i] + "</div></div>";
    }).join("");

    // 日志
    id("log").innerHTML = st.logs.length ? st.logs.map(function (x) {
      return '<div class="e ' + x.c + '">' + x.s + "</div>";
    }).join("") : '<div class="e">慢起步：挖矿获得猫砂石，购买钻头升级加速挖掘。</div>';
  }

  // ── 升级面板渲染 ──
  function renderUpgradePanel() {
    var tab = st.activeTab;
    var html = "";
    if (tab === "drill") html = renderDrillTab();
    else if (tab === "ore") html = renderOreTab();
    else if (tab === "engine") html = renderEngineTab();
    else if (tab === "auto") html = renderAutoTab();
    else if (tab === "layer") html = renderLayerTab();
    else if (tab === "perm") html = renderPermTab();
    id("upgradePanel").innerHTML = html;
    id("upgradeTabLabel").textContent = TAB_NAMES[tab];
  }

  function upgItem(label, meta, btnText, btnClass, actionData, locked, lockedMsg) {
    if (locked) {
      return '<div class="upgrade locked"><div class="upgrade-body"><div class="name"><span class="label">' +
        label + '</span></div><div class="meta">' + lockedMsg + "</div></div><button disabled>未解锁</button></div>";
    }
    return '<div class="upgrade ' + (btnClass === "can-buy" ? "affordable" : "") + '"><div class="upgrade-body"><div class="name"><span class="label">' +
      label + '</span></div><div class="meta">' + meta + '</div></div><button class="' + btnClass + '" ' + actionData + ">" + btnText + "</button></div>";
  }

  function renderDrillTab() {
    var html = "";
    for (var i = 0; i < DRILLS.length; i++) {
      var d = DRILLS[i];
      var owned = st.drillLv > i;
      var isNext = st.drillLv === i;
      var r = st.depth / effectiveCore();
      var locked = r < d.unlock;
      if (owned) {
        html += upgItem(d.name, "Lv." + (i + 1) + " · 挖掘力 ×" + Math.pow(2, i + 1).toFixed(0) + " · 已购买", "已拥有", "", "", false, "");
      } else if (isNext) {
        var aff = canAfford(d.cost);
        html += upgItem(d.name, "挖掘力 ×" + Math.pow(2, i + 1) + " · 成本: " + costText(d.cost),
          aff ? "购买" : "不足", aff ? "can-buy" : "", 'data-action="drill"', false, "");
      } else {
        html += upgItem(d.name, "挖掘力 ×" + Math.pow(2, i + 1) + " · 解锁: " + (d.unlock * 100).toFixed(0) + "%",
          "锁定", "", "", true, "深度需达到 " + (d.unlock * 100).toFixed(0) + "%");
      }
    }
    return html;
  }

  function renderOreTab() {
    var html = "";
    ORES.forEach(function (o, i) {
      if (!st.open[i]) {
        html += upgItem(o.name, "未发现 · 解锁深度 " + (o.unlock * 100).toFixed(0) + "%", "锁定", "", "", true, "深度需达到 " + (o.unlock * 100).toFixed(0) + "%");
        return;
      }
      if (st.lv[i] >= 25) {
        html += upgItem(o.name, "Lv.MAX · 产量 ×" + Math.pow(o.pg, 25).toExponential(1) + " · 已满级", "MAX", "", "", false, "");
        return;
      }
      var c = oreCost(i);
      var aff = st.stock[i] >= c;
      html += upgItem(o.name + " Lv." + st.lv[i] + "→" + (st.lv[i] + 1),
        "产量 ×" + o.pg.toFixed(2) + " · 库存 " + fmt(st.stock[i]) + " / " + fmt(c),
        aff ? "升级" : "不足", aff ? "can-buy" : "", 'data-action="ore" data-idx="' + i + '"', false, "");
    });
    return html;
  }

  function renderEngineTab() {
    var html = "";
    for (var i = 0; i < ENGINES.length; i++) {
      var e = ENGINES[i];
      var owned = st.engineLv > i;
      var isNext = st.engineLv === i;
      var r = st.depth / effectiveCore();
      var locked = r < e.unlock;
      if (owned) {
        html += upgItem(e.name, "Lv." + (i + 1) + " · 效率 ×" + Math.pow(1.3, i + 1).toFixed(2) + " · 已购买", "已拥有", "", "", false, "");
      } else if (isNext) {
        var aff = canAfford(e.cost);
        html += upgItem(e.name, "效率 ×1.3 · 成本: " + costText(e.cost),
          aff ? "购买" : "不足", aff ? "can-buy" : "", 'data-action="engine"', false, "");
      } else {
        html += upgItem(e.name, "效率 ×1.3 · 解锁: " + (e.unlock * 100).toFixed(0) + "%",
          "锁定", "", "", true, "深度需达到 " + (e.unlock * 100).toFixed(0) + "%");
      }
    }
    return html;
  }

  function renderAutoTab() {
    var html = "";
    AUTOS.forEach(function (a, i) {
      var owned = st.auto[a.key];
      var r = st.depth / effectiveCore();
      var locked = r < a.unlock;
      if (owned) {
        html += upgItem(a.name, a.text + " · 已激活", "已激活", "", "", false, "");
      } else if (locked) {
        html += upgItem(a.name, a.text + " · 解锁: " + (a.unlock * 100).toFixed(0) + "%",
          "锁定", "", "", true, "深度需达到 " + (a.unlock * 100).toFixed(0) + "%");
      } else {
        var aff = canAfford(a.cost);
        html += upgItem(a.name, a.text + " · 成本: " + costText(a.cost),
          aff ? "激活" : "不足", aff ? "can-buy" : "", 'data-action="auto" data-idx="' + i + '"', false, "");
      }
    });
    return html;
  }

  function renderLayerTab() {
    var html = "";
    LAYER_TECHS.forEach(function (t, i) {
      var owned = st.layerTech[t.key];
      var r = st.depth / effectiveCore();
      var locked = r < t.unlock;
      if (owned) {
        html += upgItem(t.name, t.text + " · 已激活", "已激活", "", "", false, "");
      } else if (locked) {
        html += upgItem(t.name, t.text + " · 解锁: " + (t.unlock * 100).toFixed(0) + "%",
          "锁定", "", "", true, "深度需达到 " + (t.unlock * 100).toFixed(0) + "%");
      } else {
        var aff = canAfford(t.cost);
        html += upgItem(t.name, t.text + " · 成本: " + costText(t.cost),
          aff ? "激活" : "不足", aff ? "can-buy" : "", 'data-action="layer" data-idx="' + i + '"', false, "");
      }
    });
    return html;
  }

  function renderPermTab() {
    var html = "";
    var cats = {};
    PERMS.forEach(function (p) { if (!cats[p.cat]) cats[p.cat] = []; cats[p.cat].push(p); });
    Object.keys(cats).forEach(function (cat) {
      html += '<div class="perm-cat">' + cat + "</div>";
      cats[cat].forEach(function (p) {
        var owned = has(p.key);
        if (owned) {
          html += upgItem(p.name, p.text + " · 已永久生效", "已购买", "", "", false, "");
        } else {
          var aff = st.shards >= p.cost;
          html += upgItem(p.name, p.text + " · 成本: " + p.cost + " 星核",
            aff ? "购买" : "不足", aff ? "can-buy" : "", 'data-action="perm" data-key="' + p.key + '"', false, "");
        }
      });
    });
    return html;
  }

  // ════════════ 初始化 ════════════
  function init() {
    beginCycle();

    id("btnStart").onclick = function () { st.mining = true; log("开始挖矿", "up"); render(); };
    id("btnStatus").onclick = render;
    id("btnStop").onclick = function () { st.mining = false; log("结束挖矿", "up"); render(); };
    id("btnDay").onclick = function () {
      if (st.depth >= effectiveCore() && !hasAuto("fullauto")) doReset();
      else advance(1 - st.dayProgress + 0.0001);
      render();
    };

    // Tab 切换
    id("tabBar").onclick = function (e) {
      var b = e.target.closest("button[data-tab]");
      if (!b) return;
      st.activeTab = b.dataset.tab;
      document.querySelectorAll("#tabBar button").forEach(function (btn) {
        btn.classList.toggle("active", btn === b);
      });
      render();
    };

    // 升级面板点击
    id("upgradePanel").onclick = function (e) {
      var b = e.target.closest("button[data-action]");
      if (!b || b.disabled) return;
      var action = b.dataset.action;
      var idx = parseInt(b.dataset.idx);
      var key = b.dataset.key;
      if (action === "ore") tryBuyOreLevel(idx, false);
      else if (action === "drill") tryBuyDrill(false);
      else if (action === "engine") tryBuyEngine(false);
      else if (action === "auto") tryBuyAuto(idx);
      else if (action === "layer") tryBuyLayerTech(idx);
      else if (action === "perm") tryBuyPerm(key);
      render();
    };

    // 速度
    document.querySelectorAll("button[data-speed]").forEach(function (b) {
      b.onclick = function () { speed = Number(b.dataset.speed); render(); };
    });

    // 重置
    id("btnReset").onclick = function () {
      st = fresh(); speed = 1; acc = 0;
      id("winModal").classList.remove("show");
      beginCycle(); render();
    };

    log("S2 v5 · 多系统升级 + 指数加速", "day");
    render();
    requestAnimationFrame(frame);
  }

  function frame(t) {
    var dt = Math.min(0.25, (t - last) / 1000);
    last = t;
    if (st.mining && !st.won) advance(speed / CFG.daySeconds * dt);
    render();
    requestAnimationFrame(frame);
  }

  // ════════════ 暴露 API ════════════
  window.S2MiningDemo = {
    config: CFG, ores: ORES, drills: DRILLS, engines: ENGINES,
    autos: AUTOS, layerTechs: LAYER_TECHS, perms: PERMS,
    snapshot: function () {
      return JSON.parse(JSON.stringify(st, function (_, v) {
        return typeof v === "bigint" ? v.toString() : v;
      }));
    },
    start: function () { st.mining = true; },
    advanceDays: function (d) { advance(d); render(); },
    firstOrder: doReset,
    reset: function () { st = fresh(); beginCycle(); render(); }
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
