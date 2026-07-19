(function () {
  "use strict";

  // S2 v3.1 · sim_v11 ACCEPT (D36 二阶通关)
  // 通关 = 累计 1e306 次一阶无限（inf1_log>=306）
  // 每次一阶后 coins 重置 + 永久加速，越来越快

  var RARITIES = ["N", "R", "SR", "SSR", "UR"];
  var ORE_NAMES = { N: "猫砂石", R: "铜须矿", SR: "紫晶猫眼", SSR: "金猫锭", UR: "虹核晶" };
  var ORE_COLORS = { N: "#64748b", R: "#2563eb", SR: "#7c3aed", SSR: "#b45309", UR: "#dc2626" };
  var PRICE = { N: 1, R: 2, SR: 4, SSR: 8, UR: 16 };

  var CFG = {
    inf_log10: 308,
    inf2_need: 306,
    d_core_log: 306,
    base_interval: 8,
    base_mining_sec: 1500,
    base_q: 1,
    base_depth: 1,
    day_seconds: 24,
    n_sim: 40,
    manual_per_day: 3,
    start_coins: 80,
    post_inf_coins: 100,
    inf1_perm: 0.55,
    depth_perm_share: 0.35,
    max_ticks_per_settle: 1e15
  };

  var SHOP_ORDER = [
    "blast", "strata", "cart", "pick", "sorter", "market",
    "shift", "chrono", "rebate",
    "belt", "brace", "lamp", "polish", "drill", "whisker", "canteen"
  ];

  // auto_base：单独购买「自动」的价格（占手动 1 次）
  var SHOP = {
    blast:  { label: "浅层爆破", desc: "往下凿", icon: "爆", kind: "depth", mult: 3, base: 15, growth: 2.4, max: 220, bump: "深度 ×3", auto_base: 200 },
    strata: { label: "岩层许可", desc: "地层系数", icon: "岩", kind: "strata", mult: 3, base: 20, growth: 2.45, max: 200, bump: "地层 ×3", auto_base: 220 },
    cart:   { label: "矿车车厢", desc: "运量", icon: "车", kind: "qty", mult: 3, base: 16, growth: 2.4, max: 220, bump: "产量 ×3", auto_base: 200 },
    pick:   { label: "镐速齿轮", desc: "挖速", icon: "镐", kind: "rate", mult: 2, base: 12, growth: 2.25, max: 200, bump: "速度 ×2", auto_base: 180 },
    sorter: { label: "分拣爪", desc: "售价", icon: "拣", kind: "value", mult: 2, base: 18, growth: 2.35, max: 180, bump: "售价 ×2", auto_base: 210 },
    market: { label: "矿市特许", desc: "全局市价", icon: "市", kind: "market", mult: 2, base: 24, growth: 2.4, max: 160, bump: "市价 ×2", auto_base: 230 },
    shift:  { label: "加班班次", desc: "日工时", icon: "班", kind: "hours", mult: 2, base: 22, growth: 2.3, max: 120, bump: "工时 ×2", auto_base: 190 },
    chrono: { label: "时序齿轮", desc: "基础间隔", icon: "时", kind: "interval", mult: 2, base: 24, growth: 2.3, max: 120, bump: "间隔 /2", auto_base: 190 },
    rebate: { label: "财税返还", desc: "结算加成", icon: "税", kind: "rebate", mult: 2, base: 28, growth: 2.35, max: 120, bump: "结算 ×2", auto_base: 240 },
    belt:   { label: "星尘传送带", desc: "再加速", icon: "带", kind: "rate", mult: 1.5, base: 32, growth: 2.3, max: 140, bump: "速度 ×1.5", auto_base: 160 },
    brace:  { label: "巷道支架", desc: "稳进尺", icon: "架", kind: "depth", mult: 1.5, base: 30, growth: 2.3, max: 140, bump: "深度 ×1.5", auto_base: 160 },
    lamp:   { label: "巷道工灯", desc: "多挖点", icon: "灯", kind: "qty", mult: 1.5, base: 30, growth: 2.3, max: 140, bump: "产量 ×1.5", auto_base: 160 },
    polish: { label: "虹核抛光", desc: "SSR/UR", icon: "光", kind: "refine", mult: 2, base: 45, growth: 2.55, max: 50, bump: "精矿 ×2", auto_base: 260 },
    drill:  { label: "猫钻头", desc: "稀有", icon: "钻", kind: "rare", mult: 1, per: 1, base: 26, growth: 2.35, max: 35, bump: "稀有↑", auto_base: 150 },
    whisker:{ label: "猫须探针", desc: "幸运", icon: "须", kind: "luck", mult: 1, per: 1, base: 28, growth: 2.4, max: 30, bump: "幸运↑", auto_base: 150 },
    canteen:{ label: "工地罐头铺", desc: "综合", icon: "罐", kind: "hybrid", mult: 1.25, qty_m: 1.25, rate_m: 1.25, depth_m: 1.25, base: 35, growth: 2.35, max: 100, bump: "全属性 ×1.25", auto_base: 250 }
  };

  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }
  function fmtSciFromLog(logV) {
    if (!isFinite(logV) || logV < -12) return "0";
    if (logV >= CFG.inf_log10 - 1e-12) return "∞";
    if (logV < 6) return String(Number(Math.pow(10, logV).toPrecision(3)));
    var exp = Math.floor(logV + 1e-12);
    return Math.pow(10, logV - exp).toFixed(2) + "e" + exp;
  }
  function coreLabel() { return "1e306"; }
  function addLog(a, b) {
    if (!isFinite(b)) return a;
    if (!isFinite(a)) return b;
    var m = Math.max(a, b);
    if (a < m - 60) return b;
    if (b < m - 60) return a;
    return m + Math.log10(Math.pow(10, a - m) + Math.pow(10, b - m));
  }
  function subLog(a, c) {
    if (!isFinite(c)) return a;
    if (!isFinite(a) || a + 1e-12 < c) return -Infinity;
    if (Math.abs(a - c) < 1e-12) return -Infinity;
    if (a > c + 60) return a;
    return a + Math.log10(1 - Math.pow(10, c - a));
  }
  function costLog(key, lv) {
    var s = SHOP[key];
    return Math.log10(s.base) + lv * Math.log10(s.growth);
  }
  function autoUnlockCostLog(key) {
    return Math.log10(SHOP[key].auto_base);
  }
  function canAfford(coins, c) {
    // 一阶后会重置 coins，不再有「∞ 预算」
    return isFinite(c) && isFinite(coins) && coins + 1e-12 >= c;
  }
  function fmtMult(m) {
    if (Math.abs(m - Math.round(m)) < 1e-9) return "×" + Math.round(m);
    return "×" + Number(m.toFixed(2));
  }
  function totalMult(mult, lv) { return lv <= 0 ? 1 : Math.pow(mult, lv); }
  function emptyOreLog() {
    var o = {};
    RARITIES.forEach(function (r) { o[r] = -Infinity; });
    return o;
  }
  function emptyLevels() {
    var o = {};
    SHOP_ORDER.forEach(function (k) { o[k] = 0; });
    return o;
  }
  function emptyBoolMap(def) {
    var o = {};
    SHOP_ORDER.forEach(function (k) { o[k] = def; });
    return o;
  }
  function isAutoBought(key) { return !!(st.auto_bought && st.auto_bought[key]); }
  function isAutoOn(key) {
    if (!isAutoBought(key)) return false;
    if (!st.auto_on || st.auto_on[key] === undefined) return true;
    return !!st.auto_on[key];
  }

  function newState() {
    return {
      day: 1, dayProgress: 0,
      coins_log: Math.log10(CFG.start_coins),
      depth_log: -Infinity,
      inf1_log: -Infinity,
      inf1_events: 0,
      lv: emptyLevels(),
      auto_bought: emptyBoolMap(false),
      auto_on: emptyBoolMap(true),
      manual_today: 0,
      auto_buys_today: 0,
      total_upgrades: 0,
      total_manual: 0,
      total_auto: 0,
      total_auto_unlocks: 0,
      total_ticks: 0,
      mining: false, holdForUpgrade: false,
      session_ticks: 0, last_segment: emptyOreLog(), last_mode: "—",
      win: false, win_day: null, logs: []
    };
  }

  function permLog() {
    if (!isFinite(st.inf1_log) || st.inf1_log < -12) return 0;
    return CFG.inf1_perm * Math.max(0, st.inf1_log);
  }

  function inf2Pct() {
    if (!isFinite(st.inf1_log) || st.inf1_log < -12) return 0;
    return clamp(100 * (st.inf1_log / CFG.inf2_need), 0, 100);
  }

  var st = newState();
  var speed = 1, lastTs = performance.now(), pendingSec = 0, renderAcc = 0, autoAcc = 0;
  var shopReady = false, rarityReady = false, oreReady = false, lastLogSig = "";
  var dirty = { hud: true, shop: true, ore: true, rarity: true, log: true };

  function markDirty(keys) {
    if (!keys || !keys.length) {
      dirty.hud = dirty.shop = dirty.ore = dirty.rarity = dirty.log = true;
      return;
    }
    keys.forEach(function (k) { dirty[k] = true; });
  }

  function rarityProbs(drill, luck) {
    var t = clamp(drill / 35, 0, 1), lk = clamp(luck / 30, 0, 1);
    var w = {
      N: Math.max(1e-9, 0.68 - 0.5 * t - 0.06 * lk),
      R: Math.max(1e-9, 0.2 - 0.04 * t),
      SR: Math.max(1e-9, 0.07 + 0.16 * t + 0.02 * lk),
      SSR: Math.max(1e-9, 0.03 + 0.22 * t + 0.04 * lk),
      UR: Math.max(1e-9, 0.02 + 0.16 * t + 0.05 * lk)
    };
    var sum = 0;
    RARITIES.forEach(function (r) { sum += w[r]; });
    var p = {};
    RARITIES.forEach(function (r) { p[r] = w[r] / sum; });
    return p;
  }

  function derive() {
    var qtyL = 0, rateL = 0, depL = 0, valL = 0, refL = 0;
    var hoursL = 0, intervalL = 0, strataL = 0, marketL = 0, rebateL = 0;
    var drill = 0, luck = 0;
    SHOP_ORDER.forEach(function (key) {
      var lv = st.lv[key] || 0;
      if (lv <= 0) return;
      var e = SHOP[key];
      if (e.kind === "qty") qtyL += lv * Math.log10(e.mult);
      else if (e.kind === "rate") rateL += lv * Math.log10(e.mult);
      else if (e.kind === "depth") depL += lv * Math.log10(e.mult);
      else if (e.kind === "value") valL += lv * Math.log10(e.mult);
      else if (e.kind === "refine") refL += lv * Math.log10(e.mult);
      else if (e.kind === "hours") hoursL += lv * Math.log10(e.mult);
      else if (e.kind === "interval") intervalL += lv * Math.log10(e.mult);
      else if (e.kind === "strata") strataL += lv * Math.log10(e.mult);
      else if (e.kind === "market") marketL += lv * Math.log10(e.mult);
      else if (e.kind === "rebate") rebateL += lv * Math.log10(e.mult);
      else if (e.kind === "rare") drill += e.per * lv;
      else if (e.kind === "luck") luck += e.per * lv;
      else if (e.kind === "hybrid") {
        qtyL += lv * Math.log10(e.qty_m);
        rateL += lv * Math.log10(e.rate_m);
        depL += lv * Math.log10(e.depth_m);
      }
    });
    var pl = permLog();
    // log 空间 ticks + 一阶永久加速（次数越多越快）
    var logTicksPerDay =
      Math.log10(CFG.base_mining_sec) + hoursL
      - Math.log10(CFG.base_interval)
      + rateL + intervalL + pl;
    var interval = CFG.base_interval / Math.max(1e-40, Math.pow(10, rateL + intervalL + pl));
    var miningSec = CFG.base_mining_sec * Math.pow(10, hoursL);
    var depthTickL = Math.log10(CFG.base_depth) + depL + strataL + pl * CFG.depth_perm_share;
    var probs = rarityProbs(drill, luck);
    var ePrice = 0;
    RARITIES.forEach(function (r) {
      var u = PRICE[r] * Math.pow(10, valL) * Math.pow(10, marketL);
      if (r === "SSR" || r === "UR") u *= Math.pow(10, refL);
      ePrice += probs[r] * u;
    });
    ePrice = Math.max(ePrice, 1e-15);
    var qtyTickL = Math.log10(CFG.base_q) + qtyL;
    var coinsTickL = qtyTickL + Math.log10(ePrice) + rebateL + pl;
    return {
      qtyLog: qtyL, rateLog: rateL, depthLog: depL, valueLog: valL, refineLog: refL,
      hoursL: hoursL, intervalL: intervalL, strataL: strataL, marketL: marketL, rebateL: rebateL,
      drillPts: drill, luckPts: luck, perm: pl,
      interval: interval, miningSec: miningSec,
      logTicksPerDay: logTicksPerDay,
      depthPerTickLog: depthTickL,
      coinsPerTickLog: coinsTickL,
      dayDepthL: logTicksPerDay + depthTickL,
      dayCoinL: logTicksPerDay + coinsTickL,
      probs: probs,
      depthPerTickDisplay: fmtSciFromLog(depthTickL)
    };
  }

  function effectLine(key, lv) {
    var meta = SHOP[key], next = lv + 1;
    if (meta.kind === "rare" || meta.kind === "luck") {
      return meta.bump + " · +" + (meta.per * lv) + "→+" + (meta.per * next);
    }
    if (meta.kind === "hybrid") {
      return "全属性 ×1.25 · 累计约 " + fmtMult(totalMult(1.25, lv));
    }
    return meta.bump + " · 累计 " + fmtMult(totalMult(meta.mult, lv)) + " → " + fmtMult(totalMult(meta.mult, next));
  }

  function hasActionableManual() {
    if (st.win || st.manual_today >= CFG.manual_per_day) return false;
    for (var i = 0; i < SHOP_ORDER.length; i++) {
      var key = SHOP_ORDER[i], meta = SHOP[key], lv = st.lv[key];
      if (lv < meta.max && canAfford(st.coins_log, costLog(key, lv))) return true;
      if (!isAutoBought(key) && canAfford(st.coins_log, autoUnlockCostLog(key))) return true;
    }
    return false;
  }

  function hasActionableAuto() {
    if (st.win) return false;
    for (var i = 0; i < SHOP_ORDER.length; i++) {
      var key = SHOP_ORDER[i];
      if (!isAutoOn(key)) continue;
      var meta = SHOP[key], lv = st.lv[key];
      if (lv >= meta.max) continue;
      if (canAfford(st.coins_log, costLog(key, lv))) return true;
    }
    return false;
  }

  function shouldHoldDay() {
    return hasActionableManual() || hasActionableAuto();
  }

  function deltaLog(key) {
    var it = SHOP[key];
    if (["qty","rate","depth","value","hours","interval","strata","market","rebate"].indexOf(it.kind) >= 0)
      return Math.log10(it.mult);
    if (it.kind === "refine") {
      var p = derive().probs;
      return Math.log10(Math.max(1.0001, 1 + (p.SSR + p.UR) * (it.mult - 1)));
    }
    if (it.kind === "hybrid") return Math.log10(it.qty_m) + Math.log10(it.rate_m) + 0.5 * Math.log10(it.depth_m);
    if (it.kind === "rare") return 0.03;
    if (it.kind === "luck") return 0.022;
    return 0.01;
  }

  function scoreLevel(key) {
    var it = SHOP[key], lv = st.lv[key];
    if (lv >= it.max) return -1e300;
    var c = Math.max(costLog(key, lv), 1e-12);
    var s = deltaLog(key) / c;
    var dlog = isFinite(st.depth_log) ? st.depth_log : -5;
    var clog = isFinite(st.coins_log) ? st.coins_log : -5;
    var depthGap = CFG.d_core_log - dlog;
    var coinGap = CFG.inf_log10 - clog;
    if (depthGap > 2) {
      if (it.kind === "depth" || it.kind === "strata") s *= 4 + Math.min(3, depthGap / 50);
      else if (it.kind === "rate" || it.kind === "interval" || it.kind === "hours") s *= 3.2 + Math.min(2.5, depthGap / 70);
      else if (it.kind === "hybrid") s *= 2;
      else if (["qty","value","market","rebate"].indexOf(it.kind) >= 0) s *= 1 + Math.min(2, Math.max(0, coinGap) / 150);
      else if (it.kind === "refine") s *= 0.45;
    } else {
      if (["qty","value","market","rebate","rate"].indexOf(it.kind) >= 0) s *= 3 + Math.min(2, Math.max(0, coinGap) / 100);
      if ((it.kind === "depth" || it.kind === "strata") && depthGap < 0.5) s *= 0.2;
    }
    if (it.kind === "rare" || it.kind === "luck") s *= st.total_upgrades > 30 ? 0.45 : 0.8;
    return s;
  }

  function doLevel(key, source) {
    if (st.win) return false;
    var meta = SHOP[key];
    if (!meta) return false;
    var lv = st.lv[key];
    if (lv >= meta.max) return false;
    if (source === "manual") {
      if (st.manual_today >= CFG.manual_per_day) return false;
    } else if (source === "auto") {
      if (!isAutoOn(key)) return false;
    } else return false;
    var c = costLog(key, lv);
    if (!canAfford(st.coins_log, c)) return false;
    st.coins_log = subLog(st.coins_log, c);
    st.lv[key] = lv + 1;
    st.total_upgrades += 1;
    if (source === "manual") {
      st.manual_today += 1;
      st.total_manual += 1;
    } else {
      st.auto_buys_today += 1;
      st.total_auto += 1;
    }
    if (source === "manual") {
      pushLog(
        "手动升级 " + meta.label + " → Lv" + st.lv[key] + " · " + meta.bump +
          " · " + ("报销 " + fmtSciFromLog(c)) +
          " · 手动 " + st.manual_today + "/" + CFG.manual_per_day,
        "up"
      );
      toast(meta.label + " " + meta.bump);
    }
    markDirty(["hud", "shop", "rarity", "log"]);
    return true;
  }

  function buyAutoUnlock(key) {
    if (st.win) return false;
    if (isAutoBought(key)) { toast("已购买自动"); return false; }
    if (st.manual_today >= CFG.manual_per_day) { toast("今日手动已满 3 次"); return false; }
    var meta = SHOP[key];
    var c = autoUnlockCostLog(key);
    if (!canAfford(st.coins_log, c)) { toast("预算不足"); return false; }
    st.coins_log = subLog(st.coins_log, c);
    st.auto_bought[key] = true;
    st.auto_on[key] = true;
    st.manual_today += 1;
    st.total_manual += 1;
    st.total_auto_unlocks += 1;
    pushLog(
      "购买自动 · " + meta.label + " · " + ("报销 " + fmtSciFromLog(c)) +
        " · 手动 " + st.manual_today + "/" + CFG.manual_per_day,
      "up"
    );
    toast(meta.label + " 自动已购");
    markDirty(["hud", "shop", "log"]);
    autoRound();
    releaseUpgradeHoldIfPossible();
    render(true);
    return true;
  }

  function toggleItemAuto(key) {
    if (!isAutoBought(key)) {
      toast("请先购买该项目的自动");
      return;
    }
    st.auto_on[key] = !isAutoOn(key);
    var on = isAutoOn(key);
    pushLog((on ? "开启" : "关闭") + "自动：" + SHOP[key].label, "day");
    toast(SHOP[key].label + " 自动：" + (on ? "开" : "关"));
    if (on) autoRound();
    releaseUpgradeHoldIfPossible();
    markDirty(["hud", "shop", "log"]);
    render(true);
  }

  /** 每波：每个已购且开启的项，最多自动 +1 级（无多段扫光） */
  function autoRound() {
    if (st.win) return 0;
    var cands = [];
    SHOP_ORDER.forEach(function (key) {
      if (!isAutoOn(key)) return;
      if (st.lv[key] >= SHOP[key].max) return;
      if (!canAfford(st.coins_log, costLog(key, st.lv[key]))) return;
      cands.push({ key: key, sc: scoreLevel(key) });
    });
    cands.sort(function (a, b) { return b.sc - a.sc; });
    var n = 0;
    cands.forEach(function (c) {
      if (doLevel(c.key, "auto")) n++;
    });
    if (n > 0) {
      releaseUpgradeHoldIfPossible();
      markDirty(["hud", "shop", "log"]);
    }
    return n;
  }

  function tryUpgrade(key) {
    if (!doLevel(key, "manual")) {
      if (st.manual_today >= CFG.manual_per_day) toast("今日手动已满 3 次");
      else if (st.lv[key] >= SHOP[key].max) toast("已达上限");
      else toast("预算不足");
      return;
    }
    autoRound();
    releaseUpgradeHoldIfPossible();
    render(true);
  }

  function updateHoldBanner() {
    var banner = document.getElementById("holdBanner");
    if (!banner) return;
    if (st.holdForUpgrade && !st.win) {
      banner.hidden = false;
      banner.classList.add("show");
      document.body.classList.add("is-holding");
      var t = document.getElementById("holdBannerText");
      if (t) {
        var parts = [];
        if (hasActionableManual()) parts.push("手动还剩 " + (CFG.manual_per_day - st.manual_today));
        if (hasActionableAuto()) parts.push("自动仍可升级");
        t.textContent = "待办：" + (parts.join(" · ") || "处理采购") + " · 用完/关自动/买不起才能过天";
      }
    } else {
      banner.hidden = true;
      banner.classList.remove("show");
      document.body.classList.remove("is-holding");
    }
  }

  function enterUpgradeHold(reason) {
    if (st.holdForUpgrade) {
      st.dayProgress = 0.999;
      autoRound();
      markDirty(["hud", "shop"]);
      updateHoldBanner();
      return;
    }
    st.holdForUpgrade = true;
    st.dayProgress = 0.999;
    pushLog("待办拦截 · 手动 " + st.manual_today + "/" + CFG.manual_per_day + " · " + (reason || ""), "warn");
    toast("待办：手动/自动采购");
    autoRound();
    markDirty(["hud", "shop", "log"]);
    updateHoldBanner();
    var shopCard = document.querySelector(".card-shop");
    if (shopCard && shopCard.scrollIntoView) {
      try { shopCard.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (e) { shopCard.scrollIntoView(true); }
    }
  }

  function releaseUpgradeHoldIfPossible() {
    if (!st.holdForUpgrade) return;
    if (shouldHoldDay()) { markDirty(["hud", "shop"]); updateHoldBanner(); return; }
    st.holdForUpgrade = false;
    updateHoldBanner();
    pushLog("待办已清 · 进入下一工作日", "day");
    markDirty(["hud", "shop", "log"]);
    if (st.dayProgress >= 0.999 - 1e-9) rolloverDay();
  }

  function randn() {
    var u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  function rollOne(probs) {
    var x = Math.random();
    for (var i = 0; i < RARITIES.length; i++) {
      x -= probs[RARITIES[i]];
      if (x <= 0) return RARITIES[i];
    }
    return "N";
  }

  /**
   * 结算 n 次 tick。
   * 关键修复：大 n 时直接用期望 log 空间，绝不截断到 2e6。
   */
  function settleTicks(n) {
    var d = derive();
    var result = {
      n: n, ore_log: emptyOreLog(), ticks_by_r: { N: 0, R: 0, SR: 0, SSR: 0, UR: 0 },
      mode: n <= CFG.n_sim ? "逐笔入账" : "批量过账",
      coins_gain_log: -Infinity, depth_gain_log: -Infinity
    };
    if (!(n > 0) || !isFinite(n)) return result;

    // 深度：log10(n) + depth_per_tick_log —— 永不截断
    result.depth_gain_log = Math.log10(n) + d.depthPerTickLog;

    var probs = d.probs, qLog = d.qtyLog;
    if (n <= CFG.n_sim) {
      var counts = { N: 0, R: 0, SR: 0, SSR: 0, UR: 0 };
      for (var i = 0; i < n; i++) counts[rollOne(probs)]++;
      var coinsLog = -Infinity;
      RARITIES.forEach(function (r) {
        result.ticks_by_r[r] = counts[r];
        if (counts[r] > 0) {
          var pl = Math.log10(PRICE[r]) + d.valueLog + d.marketL;
          if (r === "SSR" || r === "UR") pl += d.refineLog;
          result.ore_log[r] = Math.log10(counts[r]) + qLog;
          coinsLog = addLog(coinsLog, result.ore_log[r] + pl + d.rebateL);
        }
      });
      result.coins_gain_log = coinsLog;
    } else {
      // 期望结算：coins = n * qty * E[price] * rebate
      result.coins_gain_log = Math.log10(n) + d.coinsPerTickLog;
      // 展示用稀有分布
      RARITIES.forEach(function (r) {
        var c = n * probs[r];
        result.ticks_by_r[r] = c;
        if (c > 0) result.ore_log[r] = Math.log10(c) + qLog;
      });
    }
    return result;
  }

  function processFirstOrder() {
    // coins 达/超 ∞ 时折算一阶次数，重置矿币，永久加速
    if (!isFinite(st.coins_log) || st.coins_log < CFG.inf_log10 - 1e-12) return -Infinity;
    var over = st.coins_log - CFG.inf_log10;
    var gainLog = over < 0 ? 0 : (over > 15 ? over : Math.log10(1 + Math.pow(10, over)));
    st.inf1_log = addLog(st.inf1_log, gainLog);
    st.inf1_events += 1;
    st.coins_log = Math.log10(CFG.post_inf_coins);
    pushLog(
      "一阶无限 ×" + fmtSciFromLog(gainLog) +
        " · 累计一阶 " + fmtSciFromLog(st.inf1_log) +
        " / 1e306 · 永久加速 +" + permLog().toFixed(1) + " 阶 · 第" + st.inf1_events + "次冲破",
      "inf"
    );
    toast("一阶 ×" + fmtSciFromLog(gainLog) + " · 累计 " + fmtSciFromLog(st.inf1_log));
    markDirty(["hud", "shop", "log"]);
    return gainLog;
  }

  function applySegment(seg) {
    if (!(seg.n > 0)) return;
    RARITIES.forEach(function (r) { st.last_segment[r] = seg.ore_log[r]; });
    st.coins_log = addLog(st.coins_log, seg.coins_gain_log);
    st.depth_log = addLog(st.depth_log, seg.depth_gain_log);
    if (isFinite(st.depth_log) && st.depth_log > CFG.d_core_log) st.depth_log = CFG.d_core_log;
    st.total_ticks += seg.n;
    st.session_ticks += seg.n;
    st.last_mode = seg.mode;
    markDirty(["hud", "shop", "ore"]);
    processFirstOrder();
    pushLog(
      seg.mode + " · n≈" + fmtSciFromLog(Math.log10(seg.n)) +
        " · +" + fmtSciFromLog(seg.coins_gain_log) +
        " · 进尺 +" + fmtSciFromLog(seg.depth_gain_log),
      "settle"
    );
    autoRound();
    checkWin();
  }

  function depthRatio() {
    // 主进度条：二阶（一阶次数 / 1e306）
    return inf2Pct() / 100;
  }

  function checkWin() {
    if (st.win) return;
    if (isFinite(st.inf1_log) && st.inf1_log >= CFG.inf2_need - 1e-9) {
      st.win = true;
      st.win_day = st.day;
      st.mining = false;
      st.holdForUpgrade = false;
      updateHoldBanner();
      pushLog(
        "二阶无限通关 · D" + st.day +
          " · 一阶累计 " + fmtSciFromLog(st.inf1_log) +
          " · 冲破 " + st.inf1_events + " 次 · 手动" + st.total_manual +
          " 自动" + st.total_auto,
        "win"
      );
      var winText = document.getElementById("winText");
      var winModal = document.getElementById("winModal");
      if (winText) {
        winText.textContent =
          "第 " + st.day + " 日达成二阶无限。累计一阶 " + fmtSciFromLog(st.inf1_log) +
          " 次 · 冲破事件 " + st.inf1_events +
          " · 手动 " + st.total_manual + " · 自动升级 " + st.total_auto + "。";
      }
      if (winModal) winModal.classList.add("show");
      toast("二阶无限通关！");
      markDirty(["hud", "shop"]);
    }
  }

  function startMining() {
    if (st.win) { toast("已结项"); return; }
    if (st.mining) { toast("已在岗"); return; }
    st.mining = true; st.session_ticks = 0; pendingSec = 0; st.last_segment = emptyOreLog();
    pushLog("上班打卡", "up"); toast("上班打卡成功");
    markDirty(["hud", "ore"]); render(true);
  }
  function stopMining() {
    if (!st.mining) { toast("未在岗"); return; }
    flushPending();
    st.mining = false;
    pushLog("下班 · 工单 " + fmtSciFromLog(Math.log10(Math.max(st.session_ticks, 1e-12))), "up");
    toast("下班结算完成");
    markDirty(["hud"]); render(true);
  }
  function statusMining() {
    var d = derive();
    var unlocked = 0;
    SHOP_ORDER.forEach(function (k) { if (isAutoBought(k)) unlocked++; });
    pushLog(
      (st.mining ? "在岗" : "离岗") +
        " · 手动 " + st.manual_today + "/" + CFG.manual_per_day +
        " · 已购自动 " + unlocked + "/" + SHOP_ORDER.length +
        " · 今日自动升级 " + st.auto_buys_today +
        " · dd " + d.dayDepthL.toFixed(1) +
        " · 深 " + fmtSciFromLog(st.depth_log),
      "day"
    );
    toast("状态已刷新");
    markDirty(["hud"]); render(true);
  }

  function flushPending() {
    var d = derive();
    if (pendingSec < d.interval) return;
    var n = Math.floor(pendingSec / d.interval);
    // 不再截断到 2e6；仅防止极端卡死
    if (n > CFG.max_ticks_per_settle) n = CFG.max_ticks_per_settle;
    pendingSec -= n * d.interval;
    applySegment(settleTicks(n));
  }

  function rolloverDay() {
    st.day += 1;
    st.dayProgress = 0;
    st.manual_today = 0;
    st.auto_buys_today = 0;
    st.holdForUpgrade = false;
    updateHoldBanner();
    pushLog("新工作日 D" + st.day + " · 手动刷新 0/3", "day");
    markDirty(["hud", "shop", "log"]);
  }

  function skipToDayEnd() {
    if (st.win) return;
    autoRound();
    if (shouldHoldDay()) {
      enterUpgradeHold("次日拦截");
      markDirty(["hud", "shop"]); render(true); return;
    }
    st.holdForUpgrade = false; updateHoldBanner();
    advanceGameDays(Math.max(0, 1 - st.dayProgress) + 0.001, true);
    markDirty(["hud", "shop", "ore"]); render(true);
  }

  function advanceGameDays(dayDelta, forceDay) {
    if (dayDelta <= 0 || st.win) return;
    var d = derive();

    if (st.holdForUpgrade && !forceDay) {
      st.dayProgress = 0.999;
      if (st.mining) {
        pendingSec += dayDelta * d.miningSec;
        flushPending();
      } else {
        autoRound();
      }
      if (!shouldHoldDay()) releaseUpgradeHoldIfPossible();
      else updateHoldBanner();
      return;
    }

    if (st.mining) {
      pendingSec += dayDelta * d.miningSec;
      flushPending();
    }

    var left = dayDelta;
    while (left > 0 && !st.win) {
      var room = 1 - st.dayProgress;
      if (left + 1e-12 < room) { st.dayProgress += left; left = 0; break; }
      st.dayProgress = 1;
      left -= room;
      autoRound();
      if (shouldHoldDay()) {
        enterUpgradeHold(forceDay ? "强制下班拦截" : "自动下班拦截");
        st.dayProgress = 0.999;
        left = 0;
        break;
      }
      rolloverDay();
    }
  }

  function pushLog(msg, cls) {
    st.logs.unshift({ t: "D" + st.day, msg: msg, cls: cls || "" });
    if (st.logs.length > 140) st.logs.pop();
    dirty.log = true;
  }
  function toast(msg) {
    var el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toast._tm);
    toast._tm = setTimeout(function () { el.classList.remove("show"); }, 2400);
  }
  function setText(id, text) {
    var el = document.getElementById(id);
    if (el && el.textContent !== text) el.textContent = text;
  }

  function ensureOreDom() {
    var box = document.getElementById("oreGrid");
    if (!box) return null;
    if (oreReady && box.children.length === RARITIES.length) return box;
    box.innerHTML = RARITIES.map(function (r) {
      return '<div class="ore" data-r="' + r + '"><div class="name" style="color:' + ORE_COLORS[r] + '">' + r + " " + ORE_NAMES[r] +
        '</div><div class="barlet"><i data-bar style="width:0%;background:' + ORE_COLORS[r] + '"></i></div><div class="qty" data-qty>0</div></div>';
    }).join("");
    oreReady = true;
    return box;
  }
  function renderOre() {
    var box = ensureOreDom();
    if (!box) return;
    var maxLog = -Infinity;
    RARITIES.forEach(function (r) { if (isFinite(st.last_segment[r]) && st.last_segment[r] > maxLog) maxLog = st.last_segment[r]; });
    RARITIES.forEach(function (r) {
      var row = box.querySelector('[data-r="' + r + '"]');
      if (!row) return;
      var qLog = st.last_segment[r], pct = 0;
      if (isFinite(qLog) && isFinite(maxLog) && maxLog > -12) pct = 100 * Math.pow(10, clamp(qLog - maxLog, -6, 0));
      var bar = row.querySelector("[data-bar]"), qty = row.querySelector("[data-qty]");
      if (bar) bar.style.width = pct.toFixed(1) + "%";
      if (qty) qty.textContent = fmtSciFromLog(qLog);
    });
  }

  function ensureShopDom() {
    var box = document.getElementById("shop");
    if (!box) return null;
    if (shopReady && box.querySelectorAll("[data-up]").length === SHOP_ORDER.length) return box;
    box.innerHTML = SHOP_ORDER.map(function (key) {
      var m = SHOP[key];
      return '<div class="upgrade" data-shop-row="' + key + '">' +
        '<div class="upgrade-body"><div class="name"><span class="tag">' + m.icon +
        '</span><span class="label">' + m.label + '</span><span class="pill" data-lv>Lv0</span>' +
        '<span class="bump" data-bump>' + m.bump + '</span></div>' +
        '<div class="meta" data-meta></div></div>' +
        '<div class="upgrade-actions">' +
        '<button type="button" class="item-auto-btn" data-buy-auto="' + key + '">买自动</button>' +
        '<button type="button" class="item-auto-btn off" data-toggle-auto="' + key + '" hidden>自动开</button>' +
        '<button type="button" data-up="' + key + '">升级</button></div></div>';
    }).join("");
    shopReady = true;
    return box;
  }

  function renderShop() {
    var box = ensureShopDom();
    if (!box) return;
    var hardFull = st.manual_today >= CFG.manual_per_day;
    SHOP_ORDER.forEach(function (key) {
      var meta = SHOP[key], row = box.querySelector('[data-shop-row="' + key + '"]');
      if (!row) return;
      var lv = st.lv[key], cLog = costLog(key, lv), maxed = lv >= meta.max;
      var afford = canAfford(st.coins_log, cLog);
      var canBuy = !st.win && !maxed && !hardFull && afford;
      var btnLabel = "升级";
      if (maxed) btnLabel = "上限";
      else if (hardFull) btnLabel = "手动满";
      else if (!afford) btnLabel = "预算不足";
      else btnLabel = meta.bump;

      var lvEl = row.querySelector("[data-lv]");
      var metaEl = row.querySelector("[data-meta]");
      var bumpEl = row.querySelector("[data-bump]");
      var btn = row.querySelector("button[data-up]");
      var buyAutoBtn = row.querySelector("button[data-buy-auto]");
      var toggleBtn = row.querySelector("button[data-toggle-auto]");

      if (lvEl) lvEl.textContent = "Lv" + lv + "/" + meta.max;
      if (bumpEl) bumpEl.textContent = meta.bump;
      if (metaEl) {
        var cost = maxed ? "—" : fmtSciFromLog(cLog);
        var autoTxt = isAutoBought(key)
          ? (isAutoOn(key) ? " · 自动开" : " · 自动关")
          : " · 自动未购(" + fmtSciFromLog(autoUnlockCostLog(key)) + ")";
        metaEl.textContent = meta.desc + " · " + effectLine(key, lv) + " · 预算 " + cost + autoTxt;
      }
      if (btn) {
        if (btn.textContent !== btnLabel) btn.textContent = btnLabel;
        if (btn.disabled !== !canBuy) btn.disabled = !canBuy;
        btn.classList.toggle("can-buy", canBuy);
        btn.classList.toggle("need-up", canBuy && st.holdForUpgrade);
      }

      if (buyAutoBtn && toggleBtn) {
        if (isAutoBought(key)) {
          buyAutoBtn.hidden = true;
          toggleBtn.hidden = false;
          var on = isAutoOn(key);
          var t = on ? "自动开" : "自动关";
          if (toggleBtn.textContent !== t) toggleBtn.textContent = t;
          toggleBtn.classList.toggle("on", on);
          toggleBtn.classList.toggle("off", !on);
        } else {
          buyAutoBtn.hidden = false;
          toggleBtn.hidden = true;
          var uc = autoUnlockCostLog(key);
          var canUnlock = !st.win && !hardFull && canAfford(st.coins_log, uc);
          buyAutoBtn.disabled = !canUnlock;
          buyAutoBtn.textContent = canUnlock ? ("买自动 " + fmtSciFromLog(uc)) : (hardFull ? "手动满" : "买自动");
          buyAutoBtn.classList.toggle("can-buy", canUnlock);
        }
      }

      row.classList.toggle("affordable", canBuy);
      row.classList.toggle("maxed", maxed);
      row.classList.toggle("item-auto-off", isAutoBought(key) && !isAutoOn(key));
      row.classList.toggle("item-auto-ready", isAutoBought(key) && isAutoOn(key));
    });
  }

  function ensureRarityDom() {
    var box = document.getElementById("rarityBars");
    if (!box) return null;
    if (rarityReady && box.children.length === RARITIES.length) return box;
    box.innerHTML = RARITIES.map(function (r) {
      return '<div class="rb" data-r="' + r + '"><div class="rb-name" style="color:' + ORE_COLORS[r] + '">' + r +
        '</div><div class="track"><i data-bar style="width:0%;background:' + ORE_COLORS[r] + '"></i></div><div data-pct class="rb-pct">0%</div></div>';
    }).join("");
    rarityReady = true;
    return box;
  }
  function renderRarity() {
    var box = ensureRarityDom();
    if (!box) return;
    var p = derive().probs;
    RARITIES.forEach(function (r) {
      var row = box.querySelector('[data-r="' + r + '"]');
      if (!row) return;
      var pct = 100 * p[r];
      var bar = row.querySelector("[data-bar]"), pctEl = row.querySelector("[data-pct]");
      if (bar) bar.style.width = pct.toFixed(2) + "%";
      if (pctEl) pctEl.textContent = pct.toFixed(1) + "%";
    });
  }
  function renderLog() {
    var log = document.getElementById("log");
    if (!log) return;
    var sig = st.logs.length ? st.logs.length + "|" + st.logs[0].msg : "empty";
    if (sig === lastLogSig) return;
    lastLogSig = sig;
    if (!st.logs.length) {
      log.innerHTML = '<div class="e">手动 3/日 · 每项单独买自动 · 仅开关 · 深度 log 结算（可穿 1e306）</div>';
      return;
    }
    log.innerHTML = st.logs.map(function (e) {
      return '<div class="e ' + e.cls + '">[' + e.t + "] " + e.msg + "</div>";
    }).join("");
  }

  function renderHud() {
    var d = derive(), prog = depthRatio(), dayPct = clamp(st.dayProgress, 0, 1);
    var unlocked = 0;
    SHOP_ORDER.forEach(function (k) { if (isAutoBought(k)) unlocked++; });

    setText("coinsVal", fmtSciFromLog(st.coins_log));
    setText("depthVal", (isFinite(st.inf1_log) ? fmtSciFromLog(st.inf1_log) : "0") + " / 1e306");
    setText("progressVal", inf2Pct().toFixed(2) + "%");
    setText("intervalVal", d.interval < 0.01 ? d.interval.toExponential(2) + "s" : d.interval.toFixed(2) + "s");
    setText("qtyVal", fmtSciFromLog(d.qtyLog));
    setText("dptVal", d.depthPerTickDisplay);
    setText("inf1Val", isFinite(st.inf1_log) ? fmtSciFromLog(st.inf1_log) : "0");
    setText("ticksVal", fmtSciFromLog(Math.log10(Math.max(st.total_ticks, 1e-12))));
    var depthBar = document.getElementById("depthBar");
    if (depthBar) depthBar.style.width = (100 * prog).toFixed(2) + "%";
    setText("depthBarLabel", "一阶 " + (isFinite(st.inf1_log) ? fmtSciFromLog(st.inf1_log) : "0") + " / 1e306 · 冲破" + st.inf1_events);
    var dayBar = document.getElementById("dayBar");
    if (dayBar) {
      dayBar.style.width = (100 * dayPct).toFixed(1) + "%";
      dayBar.classList.toggle("hold", !!st.holdForUpgrade);
    }
    setText("dayBarLabel", st.holdForUpgrade
      ? "待办 · 手动 " + st.manual_today + "/3"
      : "工时 " + (100 * dayPct).toFixed(0) + "%");
    setText("dayPill", "D" + st.day);
    setText("infPill", "二阶 " + inf2Pct().toFixed(2) + "%");
    setText("upPill", "手动 " + st.manual_today + "/3");
    setText("autoPill", "自动 " + unlocked + "/" + SHOP_ORDER.length);
    var autoPill = document.getElementById("autoPill");
    if (autoPill) autoPill.className = "pill" + (unlocked > 0 ? " on" : "");

    var runPill = document.getElementById("runPill");
    if (runPill) {
      var text = "离岗", extra = "";
      if (st.win) { text = "已结项"; extra = " on"; }
      else if (st.holdForUpgrade) { text = "待办未清"; extra = " warn"; }
      else if (st.mining) { text = "在岗"; extra = " on"; }
      if (runPill.textContent !== text) runPill.textContent = text;
      if (runPill.className !== "pill" + extra) runPill.className = "pill" + extra;
    }
    var upPill = document.getElementById("upPill");
    if (upPill) upPill.className = "pill" + (st.holdForUpgrade ? " warn" : st.manual_today >= 3 ? " on" : "");

    setText("sessionLabel", st.holdForUpgrade
      ? "待办 手动" + st.manual_today + "/3 自动今日+" + st.auto_buys_today
      : st.mining ? "在岗" : "未打卡");
    setText("settleMode", st.last_mode + " · perm +" + d.perm.toFixed(1) + " · dc " + d.dayCoinL.toFixed(1));
    setText("speedLabel", "1日≈" + (CFG.day_seconds / speed).toFixed(1) + "s · x" + speed);

    var btnStart = document.getElementById("btnStart");
    var btnStop = document.getElementById("btnStop");
    var btnDay = document.getElementById("btnDay");
    if (btnStart) btnStart.disabled = st.win || st.mining;
    if (btnStop) btnStop.disabled = st.win || !st.mining;
    if (btnDay) {
      btnDay.classList.toggle("warn-btn", !!st.holdForUpgrade);
      btnDay.textContent = st.holdForUpgrade ? "待办" : "次日";
    }
    var shopCard = document.querySelector(".card-shop");
    if (shopCard) shopCard.classList.toggle("need-upgrade", !!st.holdForUpgrade);
    updateHoldBanner();
  }

  function render(force) {
    if (dirty.hud || force) { renderHud(); dirty.hud = false; }
    if (dirty.shop || force) { renderShop(); dirty.shop = false; }
    if (dirty.ore || force) { renderOre(); dirty.ore = false; }
    if (dirty.rarity || force) { renderRarity(); dirty.rarity = false; }
    if (dirty.log || force) { renderLog(); dirty.log = false; }
  }

  function tick(ts) {
    var dt = Math.min(0.25, (ts - lastTs) / 1000);
    lastTs = ts;
    if (!st.win) {
      advanceGameDays((speed / CFG.day_seconds) * dt, false);
      autoAcc += dt;
      if (autoAcc >= 0.5) {
        autoAcc = 0;
        if (st.mining || st.holdForUpgrade) {
          if (autoRound() > 0) dirty.hud = dirty.shop = true;
        }
      }
      if (st.mining || st.holdForUpgrade) dirty.hud = true;
      renderAcc += dt;
      if (renderAcc >= 0.2) { renderAcc = 0; render(false); }
    }
    requestAnimationFrame(tick);
  }

  function byId(id) { return document.getElementById(id); }
  function bindClick(id, fn) {
    var el = byId(id);
    if (!el) { console.error("[xqkm] missing #" + id); return false; }
    el.onclick = fn;
    return true;
  }

  function initUi() {
    var required = ["btnStart","btnStop","btnStatus","btnDay","btnReset","shop","oreGrid","log","toast","holdBanner"];
    if (required.some(function (id) { return !byId(id); })) {
      console.error("[xqkm] HTML 不匹配，请 Ctrl+F5");
      return;
    }
    bindClick("btnStart", startMining);
    bindClick("btnStop", stopMining);
    bindClick("btnStatus", statusMining);
    bindClick("btnDay", skipToDayEnd);
    document.querySelectorAll("button[data-speed]").forEach(function (btn) {
      btn.onclick = function () {
        speed = Number(btn.getAttribute("data-speed")) || 1;
        toast("速度 x" + speed);
        markDirty(["hud"]); render(true);
      };
    });
    bindClick("btnReset", function () {
      st = newState(); speed = 1; pendingSec = 0; renderAcc = 0; autoAcc = 0;
      shopReady = rarityReady = oreReady = false; lastLogSig = "";
      markDirty(); updateHoldBanner();
      var modal = byId("winModal");
      if (modal) modal.classList.remove("show");
      pushLog("新项目 · 二阶目标 1e306 次一阶 · sim_v11", "day");
      render(true);
    });
    byId("shop").addEventListener("click", function (ev) {
      var t = ev.target;
      if (!t || !t.closest) return;
      var buyA = t.closest("button[data-buy-auto]");
      if (buyA) {
        if (buyA.disabled) return;
        buyAutoUnlock(buyA.getAttribute("data-buy-auto"));
        return;
      }
      var tog = t.closest("button[data-toggle-auto]");
      if (tog) {
        toggleItemAuto(tog.getAttribute("data-toggle-auto"));
        return;
      }
      var btn = t.closest("button[data-up]");
      if (!btn || btn.disabled) return;
      tryUpgrade(btn.getAttribute("data-up"));
    });
    var goShop = byId("btnGoShop");
    if (goShop) {
      goShop.onclick = function () {
        var shopCard = document.querySelector(".card-shop");
        if (shopCard) shopCard.scrollIntoView({ behavior: "smooth", block: "start" });
      };
    }
    var sub = document.querySelector("header .sub");
    if (sub) sub.textContent = "通关=二阶(1e306次一阶) · 手动3 · 每项买自动 · ~40天";
    pushLog("S2 v3.1 · sim_v11 · 二阶无限 · 一阶越来越快", "day");
    markDirty(); render(true);
    lastTs = performance.now();
    requestAnimationFrame(tick);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initUi);
  else initUi();
})();
