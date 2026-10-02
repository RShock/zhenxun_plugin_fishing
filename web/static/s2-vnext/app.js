import { artwork, techArtwork, illustratedNotice } from "./art.js?v=s2-art-1";
import { S2Engine, loadGameData, runReplay } from "./engine.js?v=3-prestige-5";
import { renderDescription } from "./description.js?v=3-prestige-5";

const sandbox = new URLSearchParams(location.search).get("sandbox") === "1";
const STORAGE_KEY = `s2-vnext-save-v3-helper${sandbox ? "-sandbox-thirty" : ""}`;
const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 2 });
// QQ 场景下玩家更习惯中文数量级：万 / 亿 / 万亿 / 亿亿；仅在超出亿亿百倍后转科学计数法，
// 避免「深度 2.40e+19」与「核心 1.28万亿」两种风格混排造成的阅读负担。
// 每 4 位一级：万(1) 亿(2) 万亿(3) 亿亿(4) 万亿亿(5) 亿亿亿(6)……
// 全程使用中文量级，不出现 1.05e+20 这种科学计数法（群聊里没人读得懂）。
const cnUnit = (groups) => (groups % 2 ? "万" : "") + "亿".repeat(Math.floor(groups / 2));
const formatNumber = (value) => {
  if (!Number.isFinite(value)) return "∞";
  const magnitude = Math.abs(value);
  if (magnitude < 1e4) return number.format(value);
  let groups = Math.min(8, Math.floor(Math.log10(magnitude) / 4));
  while (groups > 0 && magnitude / 1e4 ** groups < 1) groups -= 1;
  while (groups < 8 && magnitude / 1e4 ** (groups + 1) >= 1) groups += 1;
  return `${number.format(value / 1e4 ** groups)}${cnUnit(groups)}`;
};
const percent = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 2 });
const coefficient = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 6 });
const $ = (selector) => document.querySelector(selector);
const formatMultiplier = (value) => `×${formatNumber(value)}`;
let data; let engine; let timer = null; let view = "construction"; let pendingOrders = []; let saveBlocked = false; let showAllPrestige = false;
const eraName = (key) => data.eras.find((item) => item.key === key)?.name || key;
const clock = (minute) => {
  const totalSeconds = Math.max(0, Math.round(Number(minute) * 60));
  const day = Math.floor(totalSeconds / 86400) + 1;
  const inDay = totalSeconds % 86400;
  const hours = Math.floor(inDay / 3600);
  const minutes = Math.floor(inDay % 3600 / 60);
  const seconds = inDay % 60;
  return `D${day} ${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}${seconds ? `:${String(seconds).padStart(2, "0")}` : ""}`;
};
const duration = (minutes) => {
  const value = Math.max(0, Number(minutes) || 0);
  if (value < 1) {
    const seconds = Math.round(value * 6000) / 100;
    return seconds < 0.01 ? "不足0.01秒" : `${number.format(seconds)}秒`;
  }
  const totalSeconds = Math.max(1, Math.round(value * 60));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor(totalSeconds % 86400 / 3600);
  const mins = Math.floor(totalSeconds % 3600 / 60);
  const seconds = totalSeconds % 60;
  const parts = [];
  if (days) parts.push(`${days}天`);
  if (hours) parts.push(`${hours}小时`);
  if (mins && parts.length < 2) parts.push(`${mins}分钟`);
  if (seconds && !days && parts.length < 2) parts.push(`${seconds}秒`);
  return parts.join("") || "0秒";
};
const notice = (text) => { $("#actionNotice").textContent = text; };
// 同一瞬间可能同时发生「挖穿 + 星区完成 + 解锁新科技」，逐条堆叠显示，别互相覆盖。
let toastLines = [];
const showToast = (text) => {
  let el = document.getElementById("graduationToast");
  if (!el) {
    el = document.createElement("div");
    el.id = "graduationToast";
    el.style.cssText = "position:fixed;right:16px;bottom:16px;max-width:380px;background:#1a1a2e;color:#fff;padding:12px 16px;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,0.3);font-size:14px;line-height:1.5;z-index:9999;transform:translateY(20px);opacity:0;transition:all .3s ease;pointer-events:none;white-space:pre-line;";
    document.body.appendChild(el);
  }
  toastLines = [...toastLines.slice(-3), text];
  el.replaceChildren(...toastLines.map(illustratedNotice));
  el.style.transform = "translateY(0)"; el.style.opacity = "1";
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.transform = "translateY(20px)"; el.style.opacity = "0"; toastLines = []; }, 4200);
};
const activeSpecs = () => data.upgrades.filter((spec) => spec.status === "active");
const manualTarget = (key) => Math.max(0, Number(engine.manualTarget(key)));
const currentPlanet = () => Number(engine.state.resets || 0) + 1;
const fullyAutomated = (source = engine) => Number(source.state.resets || 0) >= 3;

function loadSaved(seed) {
  let raw;
  try { raw = localStorage.getItem(STORAGE_KEY); }
  catch {
    $("#saveNotice").textContent = "浏览器存储不可用，本次进度无法保存。";
    return new S2Engine(data, { seed });
  }
  if (raw) {
    try {
      const payload = JSON.parse(raw);
      const restored = new S2Engine(data, { seed, state: payload });
      if (payload.state.contentVersion !== data.contentVersion) {
        try {
          localStorage.setItem(`${STORAGE_KEY}-before-${data.contentVersion}`, raw);
          $("#saveNotice").textContent = "已接续行星轮回版，旧进度已备份；现有矿井与累计统计已由新版迁移规则接续。";
        } catch {
          saveBlocked = true;
          $("#saveNotice").textContent = "旧进度可继续试玩，但备份失败，暂不覆盖原存档。";
        }
      }
      return restored;
    }
    catch (error) {
      try {
        localStorage.setItem(`${STORAGE_KEY}-backup-${Date.now()}`, raw);
        $("#saveNotice").textContent = `存档无法载入，已保留备份并新开矿井：${error.message}`;
      } catch {
        saveBlocked = true;
        $("#saveNotice").textContent = "存档无法载入且备份失败。原存档保留，本次临时进度不覆盖它。";
      }
    }
  }
  return new S2Engine(data, { seed });
}
function save() {
  if (saveBlocked) return;
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(engine.snapshot())); }
  catch (error) {
    const detail = error && error.message ? `：${error.message}` : "";
    $("#saveNotice").textContent = `进度保存失败${detail}（若为存储配额或隐私模式所致，可关闭限制后重试）`;
  }
}
function stop() { clearInterval(timer); timer = null; }
function startMining() {
  if (timer || engine.galaxyComplete()) return;
  timer = setInterval(() => advance(10), 550);
  renderStatus();
}
function advance(minutes) {
  const before = {
    credits: engine.state.credits, depth: engine.state.depth, auto: engine.state.totalAutoLevels,
    helper: engine.state.totalHelperLevels, completed: engine.state.completedPlanets, resets: engine.state.resets,
    helperReports: (engine.state.planetHistory?.length || 0), // placeholder for parity check
    era: engine.currentEra(),
    unlockedTechs: engine.unlockedCoreKeys().length,
    sectorsCleared: engine.clearedSectors(),
  };
  const beforeHelperReport = engine.state.lastHelperReport ? {...engine.state.lastHelperReport, items:[...engine.state.lastHelperReport.items]} : null;
  const beforeHelperLevels = engine.state.totalHelperLevels;
  try {
    engine.mineBlock(minutes);
    save(); render();
  } catch (error) {
    stop();
    save();
    render();
    notice(`推进失败，进度已保留：${error.message}`);
    return;
  }
  const completed = engine.state.completedPlanets - before.completed;
  const departed = engine.state.resets - before.resets;
  if (engine.galaxyComplete()) stop();
  const helperDelta = engine.state.totalHelperLevels - beforeHelperLevels;
  const parts = [`已过${duration(minutes)}`];
  // P2-7：时代只在第 1 颗星球播报。之后每颗新星球都会从原始时代重来一遍，再播就成了噪音。
  if (engine.currentEra() !== before.era && before.resets === 0 && currentPlanet() === 1) {
    parts.push(`进入【${eraName(engine.currentEra())}】`);
    showToast(`🎉 进入【${eraName(engine.currentEra())}】`);
  }
  announceMilestones(before, completed);
  if (completed > 0) parts.push(`挖穿 ${completed} 颗星球`);
  if (departed > 0) parts.push(`自动启程 ${departed} 次`);
  if (departed === 0) {
    parts.push(`深度 +${formatNumber(Math.max(0, engine.state.depth - before.depth))}`);
    const creditDelta = engine.state.credits - before.credits;
    parts.push(`矿币净变动 ${creditDelta >= 0 ? "+" : ""}${formatNumber(creditDelta)}`);
  } else {
    parts.push(`现为第 ${currentPlanet()} 颗星球`);
  }
  // 助手触发强提示（完美步进校验：所有推进都按 10分钟 settlement 逐段结算，30天一次 vs 30次一天完全一致，已用引擎自测校验）
  if (helperDelta > 0) {
    const report = engine.state.lastHelperReport;
    const names = report ? report.items.map(i=>engine.specs[i.key].name).join("、") : "";
    parts.push(`助手触发 +${helperDelta}级${names?`（${names}）`:""}`);
    // 助手已在 renderHelper 里 toast，这里再补一条更醒目的 notice 已足够
  } else {
    // 计算距离下次助手还有多久，方便测试
    const toHelper = engine.state.nextHelperMinute - engine.state.minute;
    if (!engine.state.planetComplete && engine.state.helperEnabled && toHelper > 0 && toHelper <= 4320) {
      parts.push(`距助手下班 ${duration(toHelper)}`);
    } else if (helperDelta===0 && beforeHelperReport && engine.state.lastHelperReport && engine.state.lastHelperReport.levels===0 && engine.state.lastHelperReport.minute===engine.state.minute) {
      parts.push(`助手本班无可买（${(engine.state.lastHelperReport.reason || "矿币/深度不足").replace(/。$/, "")}）`);
    }
  }
  parts.push(`自动采购 ${engine.state.totalAutoLevels - before.auto} 级`);
  if (engine.galaxyComplete()) parts.push("银河开采完成，生产已永久停止");
  else if (engine.state.planetComplete && departed === 0) parts.push("生产已停止，请手动启程");
  else {
    const checkin = nextCheckin();
    if (checkin && checkin.minute > engine.state.minute) parts.push(`下次看点 ${clock(checkin.minute)} · ${checkin.label}`);
  }
  notice(parts.join(" · "));
}
// 每一次挖穿、每一个新星区、每一项新科技都应该被玩家看见——
// 否则「自动启程」会把整局游戏唯一的爽点全部吞掉（见试玩评审 P0-4）。
function announceMilestones(before, completed) {
  const s = engine.state;
  if (completed === 1) {
    const latest = s.planetHistory?.[s.planetHistory.length - 1];
    showToast(`🪐 第 ${formatNumber(s.completedPlanets)} 颗星球挖穿！+${formatNumber(latest?.reward || 1)} 星球核心（共 ${formatNumber(s.cores)}）`);
  } else if (completed > 1) {
    showToast(`🪐 本次挖穿 ${formatNumber(completed)} 颗星球，累计 ${formatNumber(s.completedPlanets)} 颗（核心 ${formatNumber(s.cores)}）`);
  }
  for (const grant of engine.takeSectorRewards()) {
    const techName = grant.tech ? engine.coreSpecs[grant.tech.key]?.name : null;
    showToast(`🌌 星区完成：${grant.sector.name}！奖励 +${formatNumber(grant.cores)} 核心${techName ? ` · 直接装配【${techName}】Lv.${grant.tech.level}` : ""}`);
  }
  const newTechs = engine.unlockedCoreKeys().length - before.unlockedTechs;
  if (newTechs > 0) {
    const names = engine.unlockedCoreKeys().slice(-newTechs)
      .map((key) => engine.coreSpecs[key]?.name).filter(Boolean).slice(0, 3).join("、");
    showToast(`🔬 发现 ${newTechs} 项新的永久科技${names ? `：${names}${newTechs > 3 ? " 等" : ""}` : ""}`);
  }
}
function renderFinalReport() {
  const box = $("#finalReport");
  if (!engine.galaxyComplete()) { box.hidden = true; return; }
  box.hidden = false;
  const s = engine.state;
  const rows = [
    ["通关用时", `${Math.floor(s.minute / 1440) + 1} 天`],
    ["挖穿星球", `${formatNumber(s.completedPlanets)} 颗`],
    ["你的操作次数", `${formatNumber(s.totalManualCommands)} 次`],
    ["亲手建设 / 助手 / 自动", `${formatNumber(s.totalManualLevels)} / ${formatNumber(s.totalHelperLevels)} / ${formatNumber(s.totalAutoLevels)} 级`],
    ["最终永久倍率", formatMultiplier(engine.prestigeSpeed())],
    ["剩余星球核心", formatNumber(s.cores)],
  ];
  const grid = $("#finalReportGrid"); grid.replaceChildren();
  for (const [label, value] of rows) {
    const cell = document.createElement("article");
    const a = document.createElement("span"); a.textContent = label;
    const b = document.createElement("strong"); b.textContent = value;
    cell.append(a, b); grid.append(cell);
  }
  const days = Math.floor(s.minute / 1440) + 1;
  const title = s.totalManualCommands <= 30 ? "甩手掌柜" : s.totalManualCommands <= 120 ? "银河承包商" : "矿井劳模";
  renderDescription($("#finalReportTitleLine"), `称号：**${title}** · ${days} 天 / ${formatNumber(s.totalManualCommands)} 次操作挖空了一条银河。`);
}
function lockedReason(key) {
  const spec = engine.specs[key];
  const target = manualTarget(key);
  if (engine.galaxyComplete()) return "银河开采已经完成";
  if (engine.state.planetComplete) return "当前星球已挖穿，离开后可继续建设";
  if (spec.status !== "active") return "尚未开放";
  if (engine.level(key) >= spec.maxLevel) return "本代设备已满级";
  if (engine.state.autoUnlocked.includes(key)) {
    return fullyAutomated() ? "资金与前置条件满足时立即连续采购" : engine.state.resets > 0 ? "随推进结算自动采购" : "每小时参与自动采购";
  }
  if (!engine.eraUnlocked(spec.era)) {
    const era = engine.eraByKey[spec.era];
    const previous = engine.eraSequence[engine.eraSequence.indexOf(spec.era) - 1];
    return `${era.name}：深度 ${formatNumber(era.unlockDepth)}，${eraName(previous)}自动线 ${engine.eraAutomationCount(previous)}/${era.previousEraAutomations}`;
  }
  if (engine.state.depth < spec.unlockDepth) return `深度 ${formatNumber(engine.state.depth)} / ${formatNumber(spec.unlockDepth)}`;
  const missing = spec.prerequisites.filter((key) => engine.level(key) < 1);
  if (missing.length) return `前置工程：${missing.map((key) => `**${engine.specs[key].name}**`).join("、")}`;
  if (target === 0 && engine.available(key, true)) {
    const cost = engine.costFor(key);
    return engine.state.credits >= cost
      ? "已解锁；推进后立即尝试首次付费，成功后加入自动线"
      : `已解锁；首次自动采购还差 ${formatNumber(cost - engine.state.credits)} 矿币`;
  }
  if (engine.state.credits < engine.costFor(key)) return `还差 ${formatNumber(engine.costFor(key) - engine.state.credits)} 矿币`;
  return "";
}
function nextUpgradeEstimate(preferredKey) {
  if (engine.state.planetComplete || engine.galaxyComplete()) return null;
  const active = activeSpecs().filter(spec => !engine.state.autoUnlocked.includes(spec.key) && engine.level(spec.key) < spec.maxLevel);
  const incomeRate = data.rules.baseCreditsPerMinute * engine.incomeMultiplier();
  const depthRate = data.rules.baseDepthPerMinute * engine.depthMultiplier();
  // 统一口径：优先计算指定的（或与 NEXT 卡片一致的"最便宜可买"）工程，
  // 避免卡片与横幅推荐不同的"下一项"。
  if (preferredKey === undefined) {
    preferredKey = engine.manualCandidates().sort((a, b) => engine.costFor(a) - engine.costFor(b))[0] || null;
  }
  if (preferredKey && engine.specs[preferredKey]
      && !engine.state.autoUnlocked.includes(preferredKey)
      && engine.level(preferredKey) < engine.specs[preferredKey].maxLevel
      && manualTarget(preferredKey) > 0) {
    const spec = engine.specs[preferredKey];
    const needDepth = Math.max(spec.unlockDepth, engine.eraByKey[spec.era].unlockDepth);
    const depthWait = needDepth > engine.state.depth ? (needDepth - engine.state.depth) / Math.max(1e-9, depthRate) : 0;
    const cost = engine.costFor(preferredKey);
    const creditWait = cost > engine.state.credits ? (cost - engine.state.credits) / Math.max(1e-9, incomeRate) : 0;
    return { key: preferredKey, name: spec.name, wait: Math.max(depthWait, creditWait), cost, depthWait, creditWait, needDepth };
  }
  let best = null;
  let bestMinutes = Infinity;
  for (const spec of active) {
    const target = manualTarget(spec.key);
    if (target === 0) continue;
    const eraOk = engine.eraUnlocked(spec.era);
    const prereqOk = spec.prerequisites.every(k => engine.level(k) >= 1);
    if (!eraOk || !prereqOk) continue;
    const needDepth = Math.max(spec.unlockDepth, engine.eraByKey[spec.era].unlockDepth);
    const depthWait = needDepth > engine.state.depth ? (needDepth - engine.state.depth) / Math.max(1e-9, depthRate) : 0;
    const cost = engine.costFor(spec.key);
    const creditWait = cost > engine.state.credits ? (cost - engine.state.credits) / Math.max(1e-9, incomeRate) : 0;
    const wait = Math.max(depthWait, creditWait);
    if (wait < bestMinutes && wait < 4320) {
      bestMinutes = wait;
      best = { key: spec.key, name: spec.name, wait, cost, depthWait, creditWait, needDepth };
    }
  }
  if (!best) {
    const cands = engine.manualCandidates().sort((a,b)=>engine.costFor(a)-engine.costFor(b));
    if (cands.length) {
      const k = cands[0];
      const cost = engine.costFor(k);
      const wait = Math.max(0, (cost - engine.state.credits) / Math.max(1e-9, incomeRate));
      return { key: k, name: engine.specs[k].name, wait, cost, depthWait:0, creditWait: wait, needDepth: 0 };
    }
    return null;
  }
  return best;
}
// 下次看点：告诉玩家最近的"值得回来"的时刻（助手值班 / 下一工程可开工 / 解锁新时代）。
// 目标是让玩家安心离开、按点回来，而不是一直开着页面盯（QQ 群里刷屏的根源）。
function nextCheckin() {
  if (engine.state.planetComplete || engine.galaxyComplete()) return null;
  const s = engine.state;
  const candidates = [];
  if (s.helperEnabled && s.nextHelperMinute > s.minute) {
    candidates.push({ minute: s.nextHelperMinute, label: "夜班助手采购" });
  }
  const eta = nextUpgradeEstimate();
  if (eta && Number.isFinite(eta.wait) && eta.wait > 0.5) {
    candidates.push({ minute: s.minute + eta.wait, label: `「${eta.name}」可开工（按当前产速预计）` });
  }
  const eraIndex = data.eras.findIndex((item) => item.key === engine.currentEra());
  const nextEra = data.eras[eraIndex + 1];
  if (nextEra) {
    const depthRate = data.rules.baseDepthPerMinute * engine.depthMultiplier();
    if (nextEra.unlockDepth > s.depth && depthRate > 0) {
      const wait = (Number(nextEra.unlockDepth) - s.depth) / depthRate;
      // 时代解锁还受上一时代自动线数量限制，且产能会增长，仅在两周内才提示，避免误导
      if (Number.isFinite(wait) && wait > 0.5 && wait < 20160) {
        candidates.push({ minute: s.minute + wait, label: `解锁【${nextEra.name}】（按当前产速预计）` });
      }
    }
  }
  candidates.sort((a, b) => a.minute - b.minute);
  return candidates[0] || null;
}
function renderNextUpgradeBanner(container, preferredKey) {
  const eta = nextUpgradeEstimate(preferredKey);
  if (!eta) {
    container.hidden = true;
    container.textContent = "";
    return;
  }
  container.hidden = false;
  if (eta.wait < 0.5) {
    container.innerHTML = `${artwork("icon_ready").outerHTML} 下一项 <strong>${eta.name}</strong> 已可升级（${formatNumber(eta.cost)} 矿币）— 点绿色卡片立即开工`;
  } else if (eta.depthWait > eta.creditWait) {
    container.innerHTML = `${artwork("icon_wait").outerHTML} 下一项 <strong>${eta.name}</strong> 受深度限制：需挖至 ${formatNumber(eta.needDepth)}（当前 ${formatNumber(engine.state.depth)}，约 <strong>${duration(eta.depthWait)}后</strong>）`;
  } else {
    const waitText = duration(eta.wait);
    const clockText = clock(engine.state.minute + eta.wait);
    container.innerHTML = `${artwork("icon_wait").outerHTML} 下一项 <strong>${eta.name}</strong> 预计 <strong>${waitText}后</strong> 可升级（${clockText}，还差 ${formatNumber(Math.max(0, eta.cost - engine.state.credits))} 矿币）— 先去挖矿或推进时间`;
  }
}
function renderStatus() {
  const s = engine.state;
  $("#timeValue").textContent = clock(s.minute); $("#seedValue").textContent = `seed ${s.seed}`;
  $("#stationPlanet").textContent = `第 ${currentPlanet()} 颗星球`;
  $("#creditsValue").textContent = formatNumber(s.credits); $("#depthValue").textContent = formatNumber(s.depth);
  $("#incomeRate").textContent = engine.galaxyComplete()
    ? "银河开采完成，生产已永久停止"
    : s.planetComplete ? "生产已停止，等待离开星球" : `矿币收益 +${formatNumber(data.rules.baseCreditsPerMinute * engine.incomeMultiplier())} / 分钟`;
  $("#depthRate").textContent = s.planetComplete ? "深度停止增长" : `+${formatNumber(data.rules.baseDepthPerMinute * engine.depthMultiplier())} / 分钟`;
  $("#eraValue").textContent = eraName(engine.currentEra());
  $("#automationValue").textContent = `${s.autoUnlocked.length} 条自动线`;
  $("#totalBuiltValue").textContent = s.totalManualLevels + s.totalHelperLevels + s.totalAutoLevels;
  $("#purchaseCounts").textContent = `手动 ${s.totalManualLevels} · 助手 ${s.totalHelperLevels} · 自动 ${s.totalAutoLevels} · 操作 ${s.totalManualCommands}次`;
  $("#purchaseCounts").title = "操作 = 你点‘升级1级/一键建设’的总次数（批量一次算1次），用于复盘节奏；与‘级数’不同";
  $("#sceneEra").textContent = eraName(engine.currentEra());
  $("#sceneStatus").textContent = engine.galaxyComplete()
    ? "银河开采完成 · 永久停产"
    : s.planetComplete ? "星球已挖穿 · 全部生产停止" : `${s.autoUnlocked.length} 条自动线运转中`;
  // 开工之后时间永不停止：挖穿、等待启程、开关弹窗都不会让矿井静默停摆。
  // 唯一的终点是银河目标完成。
  if (engine.galaxyComplete() && timer) stop();
  const running = timer !== null;
  $("#toggleButton").textContent = engine.galaxyComplete() ? "银河开采已完成"
    : running ? "矿井运转中（时间持续流动）" : "开始挖矿游戏";
  $("#toggleButton").prepend(artwork(running ? "icon_depth" : "icon_depart"));
  $("#toggleButton").disabled = running || engine.galaxyComplete();
  $("#toggleButton").title = running
    ? "已经开工：时间会一直走下去，不需要也无法暂停"
    : "点一次就开始；之后挖穿星球、启程、看清单都不会让时间停下";
  document.querySelectorAll("[data-advance]").forEach((button) => {
    const requiresContinuous = button.dataset.continuous === "true";
    button.disabled = s.planetComplete || engine.galaxyComplete() || (requiresContinuous && !fullyAutomated());
    if (requiresContinuous) button.title = fullyAutomated() ? "全自动快速推进" : "第3次启程（全自动）后开放";
  });
  $("#planButton").disabled = s.planetComplete || engine.galaxyComplete() || !engine.chooseUpgrade("balanced");
  $("#planButton").title = $("#planButton").disabled
    ? "需要有当前买得起的工程（矿币足够支付最便宜一项）时才可用"
    : `按「${$("#routeSelect").selectedOptions[0]?.textContent || "均衡建设"}」路线一次性规划最多 ${data.rules.batchCommandMaxLevels} 级建设`;
}
function renderHelper() {
  const s = engine.state; const report = s.lastHelperReport;
  $("#helperToggle").checked = s.helperEnabled;
  $("#helperNext").textContent = s.planetComplete ? "等待下一颗星球" : s.helperEnabled ? clock(s.nextHelperMinute) : "已暂停值班";
  $("#helperCountdown").textContent = s.planetComplete ? "本星球生产与采购均已停止" : s.helperEnabled ? `还有${duration(s.nextHelperMinute - s.minute)} · 低价优先` : "装备自动采购继续运行";
  $("#helperResult").textContent = report ? `建设 ${report.levels} 级` : "等待第一班";
  if (report && report.levels > 0) {
    $("#helperResult").style.background = "#fff3cd"; $("#helperResult").style.padding = "2px 6px"; $("#helperResult").style.borderRadius = "6px";
    setTimeout(()=>{ $("#helperResult").style.background = ""; }, 1800);
    if (report.levels >= 1) showToast(`夜班助手已为你完成 ${report.levels} 级建设（${report.items.map(i=>engine.specs[i.key].name).join("、")}），省下一次手动操作。`);
  }
  $("#helperSpent").textContent = report ? `${clock(report.minute)} · 花费 ${formatNumber(report.spent)} 矿币` : "每日00:00采购";
  const root = $("#helperItems"); root.replaceChildren();
  const items = new Map();
  for (const item of report?.items || []) items.set(item.key, (items.get(item.key) || 0) + 1);
  for (const [key, levels] of items) {
    const span = document.createElement("span"); span.textContent = `${engine.specs[key].name} +${levels}`; root.append(span);
  }
  if (!items.size) root.textContent = report ? (report.reason || "本班没有新增建设。") : "值班记录尚为空。";
}
function renderNext() {
  // Early return states must not retain the previous upgrade artwork/banner.
  const previousBanner = document.getElementById("nextEtaBanner");
  if (previousBanner) previousBanner.hidden = true;
  let checkin = document.getElementById("nextCheckin");
  if (!checkin) {
    checkin = document.createElement("p");
    checkin.id = "nextCheckin";
    checkin.className = "next-checkin";
    $("#nextEta").after(checkin);
  }
  if (engine.state.planetComplete) {
    $("#nextName").textContent = engine.galaxyComplete()
      ? `${formatNumber(data.prestige.galaxyTargetPlanets)} 颗星球开采完成`
      : `第 ${currentPlanet()} 颗星球已挖穿`;
    renderDescription($("#nextReason"), engine.galaxyComplete()
      ? "**银河开采目标**已经完成，生产与启程均已永久停止。"
      : "星球核心奖励已结算，本星球不再生产。请在**行星航程**中确认重置内容并启程。");
    $("#nextProgress").value = 1;
    $("#nextProgressText").textContent = `目标深度 ${formatNumber(data.prestige.planetTargetDepth)}`;
    $("#nextEta").textContent = engine.galaxyComplete() ? "银河开采完成" : "等待离开";
    checkin.hidden = true;
    return;
  }
  const candidates = engine.manualCandidates().sort((a, b) => engine.costFor(a) - engine.costFor(b));
  const next = candidates[0] || activeSpecs().filter((spec) => !engine.state.autoUnlocked.includes(spec.key))
    .sort((a, b) => a.unlockDepth - b.unlockDepth)[0]?.key;
  if (!next) {
    const remaining = activeSpecs()
      .reduce((sum, spec) => sum + Math.max(0, spec.maxLevel - engine.level(spec.key)), 0);
    $("#nextName").textContent = remaining ? "本段工程已全部自动化" : "本段设备已全部满级";
    $("#nextReason").textContent = remaining
      ? "矿井继续生产，自动采购会在矿币足够时升级设备。"
      : "全部设备已满级，矿井继续向本星球目标深度推进。";
    $("#nextProgress").value = 1;
    $("#nextProgressText").textContent = remaining ? `还剩 ${remaining} 级自动升级` : "现有科技已全部升满";
    $("#nextEta").textContent = "";
    checkin.hidden = true;
    return;
  }
  const spec = engine.specs[next]; let current; let target; let rate; let unit;
  $("#nextName").textContent = spec.name; $("#nextName").prepend(techArtwork(spec.key)); renderDescription($("#nextReason"), lockedReason(next) || "矿币充足，可以开工");
  if (engine.available(next) || (manualTarget(next) === 0 && engine.available(next, true))) {
    current = engine.state.credits; target = engine.costFor(next);
    rate = data.rules.baseCreditsPerMinute * engine.incomeMultiplier(); unit = "矿币";
  } else {
    current = engine.state.depth; target = Math.max(spec.unlockDepth, engine.eraByKey[spec.era].unlockDepth);
    rate = data.rules.baseDepthPerMinute * engine.depthMultiplier(); unit = "挖矿深度";
  }
  $("#nextProgress").value = target ? Math.min(1, current / target) : 1;
  $("#nextProgressText").textContent = `${unit} ${formatNumber(current)} / ${formatNumber(target)}`;
  $("#nextEta").textContent = target > current ? `按当前产速约${duration((target - current) / rate)}` : "已满足数值条件";
  let banner = document.getElementById("nextEtaBanner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "nextEtaBanner";
    banner.className = "next-eta-banner";
    $("#nextReason").after(banner);
  }
  renderNextUpgradeBanner(banner, next);
  const checkinEvent = nextCheckin();
  checkin.hidden = !checkinEvent;
  if (checkinEvent) {
    checkin.textContent = `下次看点：${clock(checkinEvent.minute)} · ${checkinEvent.label} —— 在那之前可以放心离开`;
    checkin.prepend(artwork("icon_wait"));
  }
}
function buy(orders) {
  const beforeUnlocked = new Set(engine.state.autoUnlocked);
  const result = engine.upgradeCommand(orders);
  if (result.ok) {
    save(); render();
    const spent = result.purchases.reduce((sum, item) => sum + item.cost, 0);
    const eta = nextUpgradeEstimate();
    let etaText = "";
    if (eta) {
      if (eta.wait < 0.5) etaText = ` · 下一项「${eta.name}」已可升级`;
      else etaText = ` · 下一项「${eta.name}」约${duration(eta.wait)}后可升（${clock(engine.state.minute + eta.wait)}）`;
    }
    notice(`完成 ${result.purchases.length} 级建设 · 花费 ${formatNumber(spent)} 矿币${result.reason ? " · 余下工程暂未满足条件" : ""}${etaText}`);
    const newly = engine.state.autoUnlocked.filter(k=>!beforeUnlocked.has(k));
    if (newly.length) {
      const names = newly.map(k=>engine.specs[k].name).join("、");
      showToast(`🎉 ${names} 已建设到位，正式移交自动线！后续无需你再动手。`);
      // 毕业 toast 后，再提示下一次
      if (eta && eta.wait >= 0.5) setTimeout(()=> showToast(`⏳ 下一项「${eta.name}」预计 ${duration(eta.wait)}后可升级（${clock(engine.state.minute + eta.wait)}）`), 1800);
    } else if (eta) {
      if (eta.wait >= 0.5) showToast(`⏳ 已升级，下一次「${eta.name}」预计 ${duration(eta.wait)}后可升级（${clock(engine.state.minute + eta.wait)}）`);
      else if (eta.wait < 30) showToast(`✅ 已升级，「${eta.name}」已可继续升级`);
    }
  } else notice("当前条件不足，未扣除矿币。");
}
function renderTechTree() {
  const active = activeSpecs();
  const groups = {
    construction: active.filter((spec) => !engine.state.autoUnlocked.includes(spec.key) && manualTarget(spec.key) > 0 && engine.available(spec.key)),
    automated: active.filter((spec) => engine.state.autoUnlocked.includes(spec.key)),
    frontier: active.filter((spec) => !engine.state.autoUnlocked.includes(spec.key)
      && !(manualTarget(spec.key) > 0 && engine.available(spec.key))),
  };
  for (const [key, specs] of Object.entries(groups)) $(`#${key}Count`).textContent = specs.length;
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.view === view));
    button.tabIndex = button.dataset.view === view ? 0 : -1;
  });
  const root = $("#techTree"); root.replaceChildren(); root.setAttribute("aria-labelledby", `tab-${view}`);
  for (const era of data.eras) {
    const specs = groups[view].filter((spec) => spec.era === era.key);
    if (!specs.length) continue;
    const group = document.createElement("section"); group.className = "era-group";
    const header = document.createElement("header"); const title = document.createElement("h3");
    title.textContent = era.name; header.append(title); group.append(header);
    const grid = document.createElement("div"); grid.className = "tech-grid";
    for (const spec of specs) {
      const card = $("#techTemplate").content.firstElementChild.cloneNode(true);
      const commissioned = engine.state.manualLevels[spec.key]; const auto = engine.state.autoUnlocked.includes(spec.key);
      const target = manualTarget(spec.key);
      card.classList.toggle("automated", auto); card.classList.toggle("locked", view === "frontier");
      // 新增：可升/不可升配色（测试用）
      const _reasonPreview = lockedReason(spec.key);
      const canUpgrade = !_reasonPreview;
      card.classList.toggle("can-upgrade", canUpgrade && view === "construction" && !auto);
      card.classList.toggle("cannot-upgrade", !canUpgrade && view === "construction" && !auto);
      const h3 = card.querySelector("h3");
      h3.textContent = spec.name;
      h3.prepend(techArtwork(spec.key));
      // 已有 eta badge 清理
      const oldBadge = h3.querySelector(".eta-badge");
      if (oldBadge) oldBadge.remove();
      if (view === "construction" && !auto) {
        const badge = document.createElement("span");
        badge.className = "eta-badge";
        if (canUpgrade) {
          badge.textContent = "可升级";
          badge.style.background = "#126650";
        } else {
          // 计算该项的等待时间，仅当是“钱不够”时显示倒计时
          if (_reasonPreview.startsWith("还差")) {
            const cost = engine.costFor(spec.key);
            const incomeRate = data.rules.baseCreditsPerMinute * engine.incomeMultiplier();
            const wait = Math.max(0, (cost - engine.state.credits) / Math.max(1e-9, incomeRate));
            if (wait < 0.5) badge.textContent = "可升";
            else if (wait < 1440) badge.textContent = `${duration(wait)}后`;
            else badge.textContent = `${Math.ceil(wait/60)}小时后`;
            badge.style.background = "#8a9a94";
          } else {
            badge.textContent = "未解锁";
            badge.style.background = "#b0bec5";
          }
        }
        h3.appendChild(badge);
      }
      const strength = Number(engine.effectStrength(spec.effectKind));
      const enhanced = Math.abs(strength - 1) >= 1e-9;
      const descriptionLabel = card.querySelector(".description-label");
      descriptionLabel.hidden = !enhanced;
      renderDescription(card.querySelector(".description"), spec.description);
      const strengthLine = card.querySelector(".tech-strength");
      strengthLine.hidden = !enhanced;
      if (enhanced) {
        const baseCoefficient = Number(spec.effectPerLevel);
        const coefficientFormat = spec.effectKind === "speed_compound" ? percent : coefficient;
        renderDescription(strengthLine, `永久强化后：**单级系数 ${coefficientFormat.format(baseCoefficient)} → ${coefficientFormat.format(baseCoefficient * strength)}**（已计入实际效果）`);
      }
      card.querySelector(".level-chip").textContent = `Lv.${engine.level(spec.key)} / ${spec.maxLevel}`;
      card.querySelector(".region").textContent = data.multiplierRegions.find((item) => item.key === spec.region)?.name || spec.region;
      card.querySelector(".cost").textContent = engine.level(spec.key) >= spec.maxLevel ? "已满级" : `${formatNumber(engine.costFor(spec.key))} 矿币`;
      const progressLabel = card.querySelector(".progress-label");
      progressLabel.textContent = auto ? "已自动化" : target === 0 ? "本星球直接自动建设" : `亲手建设 ${commissioned} / ${target}`;
      if (!auto && target > 0) progressLabel.title = "前几级需要你亲手建；建满之后这台设备就交给矿井，自动一直升下去";
      const progress = card.querySelector(".manual-progress");
      progress.replaceChildren();
      progress.hidden = target === 0;
      progress.style.setProperty("--manual-steps", Math.max(1, target));
      for (let index = 0; index < target; index += 1) {
        const dot = document.createElement("i"); dot.classList.toggle("filled", index < commissioned); progress.append(dot);
      }
      const reason = lockedReason(spec.key);
      const upgrade = card.querySelector(".upgrade-button"); upgrade.disabled = Boolean(reason);
      upgrade.addEventListener("click", () => buy([[spec.key, 1]]));
      const remaining = Math.max(0, target - commissioned);
      upgrade.title = remaining > 0
        ? `再亲手建 ${remaining} 级，这台设备就会转给矿井自动升级`
        : "这台设备已经交给矿井自动升级";
      renderDescription(card.querySelector(".lock-reason"), reason || `再亲手建 ${remaining} 级后转为自动`);
      grid.append(card);
    }
    group.append(grid); root.append(group);
  }
  if (!root.children.length) {
    const p = document.createElement("p"); p.className = "empty";
    if (engine.state.planetComplete) {
      p.textContent = "当前星球已挖穿，生产与采购均已停止；启程后可在下一颗星球重新建设。";
    } else {
      p.textContent = view === "construction"
        ? groups.frontier.length ? "当前装备已交给自动生产线。矿井正在接近下一项工程。" : "本段工程均已自动化，矿井继续生产。"
        : view === "automated" ? "尚无自动生产线。" : "当前阶段的工程均已发现。";
    }
    root.append(p);
  }
}
function renderMultipliers() {
  const root = $("#multiplierList"); root.replaceChildren();
  Object.entries(engine.multiplierBreakdown()).filter(([, value]) => value > 1.000001).forEach(([key, value]) => {
    const region = data.multiplierRegions.find((item) => item.key === key || item.key === key.replace("_", ""));
    const row = document.createElement("div"); const label = document.createElement("span"); const count = document.createElement("b");
    const prestigeNames = {
      prestige: "永久科技倍率",
      stellar_relay: "联合勘探",
      opening_burst: "新星首秒大爆发",
      completion_depth: "全科技满级深度",
    };
    label.textContent = key === "critical" ? "暴击期望" : prestigeNames[key] || region?.name || key; count.textContent = formatMultiplier(value); row.append(label, count); root.append(row);
  });
  const discount = engine.coreEffect("local_discount");
  if (discount > 0) {
    const row = document.createElement("div"); const label = document.createElement("span"); const count = document.createElement("b");
    label.textContent = "本地设备成本";
    count.textContent = `${formatMultiplier(1 / (1 + discount))} 原价`;
    row.append(label, count); root.append(row);
  }
  $("#incomeMultiplier").textContent = formatMultiplier(engine.incomeMultiplier());
  $("#depthMultiplier").textContent = formatMultiplier(engine.depthMultiplier());
}
function thresholdSummary(source = engine) {
  const targets = activeSpecs().map((spec) => Math.max(0, Number(source.manualTarget(spec.key))));
  const low = Math.min(...targets); const high = Math.max(...targets);
  if (high === 0) return "0级（全自动）";
  return low === high ? `亲手 ${high} 级` : `亲手 ${low}–${high} 级`;
}
function departurePreview() {
  if (!engine.state.planetComplete || engine.galaxyComplete()) return null;
  const copy = new S2Engine(data, { state: engine.snapshot() });
  const result = copy.departPlanet();
  return result.ok ? { speed: copy.prestigeSpeed(), threshold: thresholdSummary(copy) } : null;
}
function coreGroup(spec) {
  if (Number(spec.unlockResets) <= 1) return ["planet", "行星技术"];
  if (Number(spec.unlockResets) <= 5) return ["star", "恒星系技术"];
  return ["galaxy", "银河技术"];
}
const coreStage = {
  planet_drive: "适合阶段：**全航程**，尤其是新星空矿井与早期重建。",
  core_drill: "适合阶段：**每颗星球的设备重建期**，速度科技等级逐步增多后更明显。",
  core_refining: "适合阶段：**前中期攒矿币与重复建设**；它不直接增加深度。",
  core_depth: "适合阶段：**设备成型后的冲深期**；它不直接增加矿币。",
  stellar_forge: "适合阶段：**本地科技种类与等级较多后**，不强化速度和暴击率。",
  stellar_relay: "适合阶段：**自动线逐步建成后**；新星开始时需重新建设自动线。",
  galactic_drive: "适合阶段：**全航程与跨星推进**，每4级合计翻倍。",
  stellar_procurement: "适合阶段：**每颗新星的重建期**，只降低本地设备矿币成本。",
  planetary_exhaustion: "适合阶段：**前中期全部本地科技满级后的冲深**；后期重建时间占主导，整段航程收益会减弱。",
  big_bang: "适合阶段：**极短的后期航程**；只覆盖抵达新星后的首1秒。",
};
function coreEffectSummary(spec, level) {
  const nextLevel = Math.min(spec.maxLevel, level + 1);
  const current = coreEffectAtLevel(spec, level);
  if (level >= spec.maxLevel) return `当前：**${current}** · 已满级`;
  return `当前：**${current}** · 下级：**${coreEffectAtLevel(spec, nextLevel)}**`;
}
function coreEffectAtLevel(spec, level) {
  const amount = Number(spec.effectPerLevel) * level;
  switch (spec.effectKind) {
    case "global_linear":
      return `矿币与深度 ${formatMultiplier(1 + amount)}`;
    case "global_speed":
      return `矿币与深度 ${formatMultiplier(2 ** amount)}`;
    case "speed_strength":
      return `速度科技单级强度 +${percent.format(amount)}`;
    case "income_strength":
      return `收入类单级强度 +${percent.format(amount)}`;
    case "depth_strength":
      return `深度类单级强度 +${percent.format(amount)}`;
    case "equipment_strength":
      return `适用本地科技单级强度 +${percent.format(amount)}`;
    case "line_synergy":
      return `每条自动线 +${percent.format(amount)}`;
    case "local_discount":
      return `本地成本 ÷${number.format(1 + amount)}（${percent.format(1 / (1 + amount))} 原价）`;
    case "completion_depth":
      return level ? `全满级后深度 ${formatMultiplier(1 + amount)}` : "全满级后深度效果未启用";
    case "opening_burst":
      return level ? `新星首1秒 ${formatMultiplier(1 + amount)}` : "新星首1秒效果未启用";
    default:
      return level ? `效果强度 ${number.format(amount)}` : "效果未启用";
  }
}
function coreUnavailableReason(spec, level, cost) {
  if (level >= spec.maxLevel) return "已满级";
  if (engine.state.completedPlanets < spec.unlockResets) return `完成 ${spec.unlockResets} 颗星球后解锁`;
  if (engine.state.cores < cost) return `还差 ${formatNumber(cost - engine.state.cores)} 星球核心`;
  return "";
}
function coreGroupRequirement(specs) {
  const gates = specs.map((spec) => Number(spec.unlockResets));
  const low = Math.min(...gates); const high = Math.max(...gates);
  return low === high ? `完成 ${low} 颗星球` : `完成 ${low}–${high} 颗星球`;
}
function buyCore(key) {
  const result = engine.purchaseCore(key);
  if (!result.ok) {
    const reasons = { locked: "永久科技尚未解锁。", cores: "星球核心不足，未进行购买。", max: "这项永久科技已满级。" };
    notice(reasons[result.reason] || "当前无法购买这项永久科技。");
    renderPrestige();
    return;
  }
  save(); render();
  const left = engine.coreManualTarget(key);
  notice(result.commissioned
    ? `永久科技升级至 Lv.${result.level} · 消耗 ${formatNumber(result.cost)} 星球核心——亲手建设已达标，这项科技转入自动线，之后矿井自己升。`
    : `永久科技升级至 Lv.${result.level} · 消耗 ${formatNumber(result.cost)} 星球核心（再亲手 ${left} 级转自动）`);
}
function renderCoreShop() {
  const root = $("#coreShop"); root.replaceChildren();
  const upgrades = data.prestige?.upgrades || [];
  $("#coreShopTitle").textContent = `星球核心技术（${upgrades.length}项）`;
  // 混合展示：默认只显示已解锁 + 临近5颗内可预览的，远期折叠，避免二阶段全摊开的压迫感
  const nearThreshold = 5;
  const filteredUpgrades = showAllPrestige ? upgrades : upgrades.filter(s => s.unlockResets <= engine.state.completedPlanets + nearThreshold || engine.state.coreLevels[s.key] > 0);
  const hiddenCount = upgrades.length - filteredUpgrades.length;
  // 顶部切换按钮
  const controls = document.createElement("div");
  controls.className = "core-shop-controls";
  controls.style.cssText = "display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap";
  const info = document.createElement("small");
  info.style.color = "var(--muted)";
  info.textContent = showAllPrestige ? `已展示全部 ${upgrades.length} 项` : `已展示 ${filteredUpgrades.length} 项，隐藏 ${hiddenCount} 项远期科技（完成更多星球后逐步解锁）`;
  const toggle = document.createElement("button");
  toggle.textContent = showAllPrestige ? "收起远期科技" : `展开全部 ${upgrades.length} 项`;
  toggle.style.cssText = "padding:6px 10px;font-size:12px";
  toggle.addEventListener("click", () => { showAllPrestige = !showAllPrestige; renderCoreShop(); });
  controls.append(info, toggle);
  root.append(controls);
  const displayUpgrades = filteredUpgrades;
  const grouped = new Map([["planet", []], ["star", []], ["galaxy", []]]);
  const labels = new Map();
  for (const spec of displayUpgrades) {
    const [key, label] = coreGroup(spec); grouped.get(key).push(spec); labels.set(key, label);
  }
  for (const [groupKey, specs] of grouped) {
    if (!specs.length) continue;
    const group = document.createElement("section"); group.className = "core-group";
    const heading = document.createElement("div"); heading.className = "core-group-heading";
    const title = document.createElement("h3"); title.textContent = labels.get(groupKey);
    const unlock = document.createElement("span");
    unlock.textContent = coreGroupRequirement(specs);
    heading.append(title, unlock); group.append(heading);
    const grid = document.createElement("div"); grid.className = "core-grid";
    for (const spec of specs) {
      const level = Number(engine.state.coreLevels?.[spec.key] || 0);
      const cost = Number(engine.coreCost(spec.key));
      const available = Boolean(engine.coreAvailable(spec.key));
      const reason = coreUnavailableReason(spec, level, cost);
      const card = document.createElement("article"); card.className = "core-card";
      card.classList.toggle("core-locked", engine.state.completedPlanets < spec.unlockResets);
      // 近期预览但未解锁的卡片加虚线边框，提示“即将解锁”
      if (!showAllPrestige && engine.state.completedPlanets < spec.unlockResets && spec.unlockResets <= engine.state.completedPlanets + nearThreshold) {
        card.style.borderStyle = "dashed";
        card.style.borderColor = "#8a9a94";
      }
      const top = document.createElement("div"); top.className = "tech-top";
      const gate = document.createElement("span"); gate.textContent = `完成 ${spec.unlockResets} 颗星球`;
      const levelChip = document.createElement("span"); levelChip.className = "level-chip"; levelChip.textContent = `Lv.${level} / ${spec.maxLevel}`;
      top.append(gate, levelChip);
      const hand = Number(engine.state.coreManualLevels?.[spec.key] || 0);
      const commissioned = engine.coreCommissioned(spec.key);
      const channel = document.createElement("span"); channel.className = "level-chip";
      channel.textContent = commissioned ? "已转自动" : `亲手 ${hand} / ${engine.coreCommissionLevels}`;
      top.append(channel);
      const name = document.createElement("h3"); name.textContent = spec.name;
      name.prepend(techArtwork(spec.key));
      const description = document.createElement("p"); description.className = "description";
      renderDescription(description, spec.description);
      const permanent = document.createElement("p"); permanent.className = "permanent-note";
      renderDescription(permanent, coreEffectSummary(spec, level));
      const stage = document.createElement("p"); stage.className = "core-stage";
      renderDescription(stage, coreStage[spec.key] || "适合阶段：按当前航程需求选择。");
      const actions = document.createElement("div"); actions.className = "core-actions";
      const status = document.createElement("small");
      status.textContent = commissioned
        ? `已亲手建设 ${engine.coreCommissionLevels} 级，之后由自动线继续升级（核心够就买）`
        : reason || `可用星球核心 ${formatNumber(engine.state.cores)}`;
      const button = document.createElement("button"); button.className = "primary";
      button.textContent = level >= spec.maxLevel ? "已满级"
        : commissioned ? "已交给自动线" : `亲手购买 · ${formatNumber(cost)} 星球核心`;
      button.disabled = !available || engine.state.cores < cost; button.addEventListener("click", () => buyCore(spec.key));
      actions.append(status, button); card.append(top, name, description, permanent, stage, actions); grid.append(card);
    }
    group.append(grid); root.append(group);
  }
  if (hiddenCount > 0 && !showAllPrestige) {
    const more = document.createElement("p");
    more.className = "empty";
    more.textContent = `还有 ${hiddenCount} 项超科幻科技在更远的星海中等待（需完成更多星球），点击“展开全部”可提前预览全部 50 项。`;
    root.append(more);
  }
  if (!displayUpgrades.length) {
    const empty = document.createElement("p"); empty.className = "empty"; empty.textContent = "永久科技数据尚未载入。"; root.append(empty);
  }
}
function renderHistory() {
  const root = $("#planetHistory"); root.replaceChildren();
  const history = [...(engine.state.planetHistory || [])].reverse().slice(0, 6);
  for (const item of history) {
    const row = document.createElement("li");
    const main = document.createElement("span"); main.textContent = `第 ${item.planet} 颗 · ${duration(item.minutes)}`;
    const details = document.createElement("small");
    const parts = [`+${formatNumber(item.reward)} 星球核心`];
    if (item.allMaxedMinute !== null) {
      parts.push(`全满级后冲刺 ${duration(Number(item.completedMinute) - Number(item.allMaxedMinute))}`);
    }
    details.textContent = parts.join(" · "); row.append(main, details); root.append(row);
  }
  $("#historyEmpty").hidden = history.length > 0;
}
function renderSector() {
  const info = engine.sectorProgress();
  if (!info) return;
  const { sector, from, target, done, index, total, ratio } = info;
  $("#sectorName").textContent = `星区 ${index + 1}/${total} · ${sector.name}`;
  $("#sectorCount").textContent = engine.galaxyComplete() ? "全部完成" : `已挖穿 ${formatNumber(done)} 颗`;
  $("#sectorProgress").value = ratio;
  $("#sectorProgressText").textContent = `本星区 ${formatNumber(Math.max(0, done - from))} / ${formatNumber(target - from)} 颗（${percent.format(ratio)}）`;
  // 只有真的代买科技（rewardTechLevels > 0）时才写科技名，否则纯发核心、买什么由玩家决定
  const rewardTech = Number(sector.rewardTechLevels) > 0 ? engine.coreSpecs[sector.rewardTechKey]?.name : "";
  $("#sectorReward").textContent = engine.galaxyComplete() ? "银河开采完成"
    : `完成奖励：+${formatNumber(sector.rewardCores)} 核心${rewardTech ? ` · 【${rewardTech}】` : "（买什么由你决定）"}`;
  $("#sectorFlavor").textContent = sector.flavor || "";
}
function renderPrestige() {
  const s = engine.state;
  const target = Number(data.prestige.planetTargetDepth);
  const completed = s.planetComplete
    ? [...(s.planetHistory || [])].reverse().find((item) => item.planet === currentPlanet())
    : null;
  const elapsed = completed ? Number(completed.minutes) : Math.max(0, s.minute - s.planetStartedMinute);
  const progress = target > 0 ? Math.min(1, s.depth / target) : 0;
  $("#planetTitle").textContent = `第 ${currentPlanet()} 颗星球`;
  $("#planetState").textContent = engine.galaxyComplete()
    ? "银河目标完成 · 永久停产"
    : s.planetComplete ? "已挖穿 · 等待启程" : "开采进行中";
  $("#planetProgress").value = progress;
  $("#planetProgressText").textContent = `深度 ${formatNumber(Math.min(s.depth, target))} / ${formatNumber(target)}${progress >= 0.0001 ? `（${percent.format(progress)}）` : ""}`;
  $("#planetElapsed").textContent = `本星球 ${duration(elapsed)}`;
  $("#coresValue").textContent = formatNumber(s.cores);
  $("#resetsValue").textContent = formatNumber(s.resets);
  $("#completedValue").textContent = formatNumber(s.completedPlanets);
  $("#prestigeSpeed").textContent = formatMultiplier(engine.prestigeSpeed());
  $("#prestigeThreshold").textContent = thresholdSummary();
  renderSector();
  const galaxyProgress = Number(data.prestige.galaxyTargetPlanets) > 0
    ? Math.min(1, s.completedPlanets / Number(data.prestige.galaxyTargetPlanets)) : 0;
  renderDescription($("#galaxyGoalNote"), `**银河目标**：七个星区、累计挖穿 **${formatNumber(data.prestige.galaxyTargetPlanets)} 颗星球**（已完成 ${percent.format(galaxyProgress)}）。每挖穿一颗，星球核心与永久科技都会让下一颗更快；新的永久科技会**一直解锁到最后一个星区**——按自己的节奏来就好。`);
  const prestigeUnlocked = s.completedPlanets > 0;
  $("#prestigeLockedReward").hidden = prestigeUnlocked;
  $("#departurePanel").hidden = !prestigeUnlocked;
  $("#prestigeContent").hidden = !prestigeUnlocked;
  const stellarRelay = Number(engine.multiplierBreakdown().stellar_relay || 1);
  renderDescription($("#permanentSummary"), `**永久科技倍率** ${formatMultiplier(engine.prestigeSpeed())} · **联合勘探** ${formatMultiplier(stellarRelay)}`);
  // 核心闲置提示：托管关闭且核心足够购买最便宜的永久科技时提醒玩家行动。
  // 背景：纯挂机会让核心一直攒着不消费，永久倍率停在 ×1，银河目标实际不可达（详见试玩评审）。
  let coreIdleHint = document.getElementById("coreIdleHint");
  if (!coreIdleHint) {
    coreIdleHint = document.createElement("p");
    coreIdleHint.id = "coreIdleHint";
    coreIdleHint.className = "core-idle-hint";
    $("#permanentSummary").after(coreIdleHint);
  }
  let cheapestCore = null;
  for (const spec of data.prestige.upgrades || []) {
    if (!engine.coreAvailable(spec.key)) continue;
    const cost = engine.coreCost(spec.key);
    if (!cheapestCore || cost < cheapestCore.cost) cheapestCore = { name: spec.name, cost };
  }
  const coreIdle = Boolean(cheapestCore) && !s.coreHelperEnabled
    && s.cores >= cheapestCore.cost && !engine.galaxyComplete();
  coreIdleHint.hidden = !coreIdle;
  if (coreIdle) {
    renderDescription(coreIdleHint, `**${formatNumber(s.cores)} 个星球核心闲置中**——核心放着不会自己变强。现在就可以亲手购买「**${cheapestCore.name}**」（${formatNumber(cheapestCore.cost)} 核心），或把上方的「**永久科技夜班助手**」打开，让它替你把核心花掉。`);
    coreIdleHint.prepend(artwork("icon_research"));
  }
  const allMaxed = s.allMaxedMinute === null ? null : Math.max(0, Number(s.allMaxedMinute) - Number(s.planetStartedMinute));
  $("#allMaxedStatus").textContent = allMaxed === null
    ? engine.allLocalMaxed() ? "设备已满级，旧进度未记录满级时刻" : "设备尚未全部满级"
    : `全部满级于本轮 ${duration(allMaxed)}`;

  const announcement = $("#completionAnnouncement");
  announcement.hidden = !s.planetComplete;
  if (s.planetComplete) {
    renderDescription(announcement, engine.galaxyComplete()
      ? `第 **${formatNumber(data.prestige.galaxyTargetPlanets)}** 颗星球已经挖穿，银河开采正式完结。生产与启程均已永久停止。`
      : `第 ${currentPlanet()} 颗星球已经挖穿，${completed ? `**${formatNumber(completed.reward)} 星球核心**已发放一次` : "**星球核心奖励**已发放一次"}。本星球生产已停止。`);
  }

  const preview = departurePreview();
  $("#departButton").hidden = !s.planetComplete || engine.galaxyComplete();
  $("#departButton").disabled = !preview || engine.galaxyComplete();
  if (preview) {
    // 计算启程前后单星预估秒数对比 — 仅全自动后 voyagePlan 才精确，早期间离散步进误差极大
    let beforeSec = null, afterSec = null;
    let secLine = "";
    try {
      if (fullyAutomated() && engine.state.resets >= 3) {
        const beforePlan = engine.voyagePlan();
        const copyAfter = new S2Engine(data, { state: engine.snapshot() });
        copyAfter.departPlanet();
        const afterPlan = copyAfter.voyagePlan();
        if (Number.isFinite(beforePlan.duration) && Number.isFinite(afterPlan.duration) && beforePlan.duration < 1e9 && afterPlan.duration < 1e9 && beforePlan.duration > 0 && afterPlan.duration > 0) {
          beforeSec = beforePlan.duration * 60;
          afterSec = afterPlan.duration * 60;
          secLine = ` 本星预估 ${duration(beforeSec/60)} → 下星 ${duration(afterSec/60)}（提速 ${Math.round((1-afterSec/beforeSec)*100)}%）。`;
        }
      } else {
        secLine = ` 早期间为10分钟离散结算，秒级预估仅在全自动（第3次启程）后生效。`;
      }
    } catch {}
    renderDescription($("#departureDescription"), `启程会重置**矿币、深度、全部设备和全部本地科技等级**；保留**星球核心、永久科技、累计建设等级与操作次数**（操作次数=你点“升级”按钮的次数，批量一次算1次，用于复盘节奏）。下一颗星球基础开采速度 ${formatMultiplier(preview.speed)}，每项设备**亲手建设 ${preview.threshold}** 后转入自动线。${secLine}`);
  } else {
    renderDescription($("#departureDescription"), engine.galaxyComplete()
      ? `本银河的 **${formatNumber(data.prestige.galaxyTargetPlanets)} 颗星球**已全部开采完成，生产与启程均已永久停止；**星球核心、永久科技、累计总级数与操作次数**完整保留。`
      : `挖穿目标深度后可前往下一颗星球。启程会重置**全部设备和全部本地科技等级**；**星球核心、永久科技、累计总级数（手动+助手+自动）与操作次数**会保留。当前永久基础速度 ${formatMultiplier(engine.prestigeSpeed())}，本星每项设备要**${thresholdSummary()}**才会转入自动线。`);
  }
  $("#autoDepartToggle").checked = s.autoDepart;
  $("#autoDepartToggle").disabled = engine.galaxyComplete();
  const quota = engine.manualDepartureQuota();
  $("#autoDepartHint").textContent = engine.galaxyComplete()
    ? "银河目标已经完成，自动启程不再生效。"
    : s.resets < quota
      ? `前 ${quota} 次启程都要你亲手点（已完成 ${s.resets}/${quota}）——每一次挖穿都值得你亲眼看一下。第 ${quota + 1} 次起才会自动。`
      : s.autoDepart ? "后续星球完成时自动启程；每次挖穿仍会播报。" : "后续星球完成后会停下，等待手动启程。";
  $("#coreHelperToggle").checked = s.coreHelperEnabled !== false;
  $("#coreHelperToggle").disabled = engine.galaxyComplete();
  const commissionedCount = s.coreAutoUnlocked?.length || 0;
  const unlockedCount = engine.unlockedCoreKeys().length;
  $("#coreHelperHint").textContent = engine.galaxyComplete()
    ? "银河目标已经完成，不再需要采购。"
    : `永久科技和本地设备同一条规则：每项亲手建设 ${engine.coreCommissionLevels} 级，之后自动线接手，核心够就自己升。`
      + `目前 ${commissionedCount}/${unlockedCount} 项已转自动。`
      + (s.coreHelperEnabled
        ? "夜班助手开着：你不管的时候，它会从最便宜的那项开始把核心花掉，也包括替你凑前 3 级。"
        : "夜班助手已关：还没转自动的科技要你亲手买，核心会一直攒着。");
  renderCoreShop(); renderHistory();
}
let resumeMiningAfterDialog = false;
// 打开模态弹窗前记录连续挖矿状态；关闭弹窗后自动恢复，避免"静默暂停"
function pauseForDialog() {
  resumeMiningAfterDialog = timer !== null;
  if (resumeMiningAfterDialog) stop();
  renderStatus();
}
function maybeResumeMining() {
  if (!resumeMiningAfterDialog) return;
  resumeMiningAfterDialog = false;
  if (timer || engine.state.planetComplete || engine.galaxyComplete()) return;
  timer = setInterval(() => advance(10), 550);
  renderStatus();
}
function previewPlan() {
  pauseForDialog();
  const copy = new S2Engine(data, { state: engine.snapshot() });
  pendingOrders = [];
  // 「一键建设」= 和夜班笨助手同一套笨办法：从最便宜的开始买，一直买到钱不够为止。
  // 它不聪明、也不会留钱做规划——省力就不该同时拿到最优解。
  for (let guard = 0; guard < 5000; guard += 1) {
    const key = copy.chooseUpgrade("cheapest");
    if (!key) break;
    const result = copy.upgradeCommand([[key, 1]]);
    if (!result.ok) break;
    pendingOrders.push([key, 1]);
  }
  const spent = engine.state.credits - copy.state.credits; const items = new Map();
  for (const [key] of pendingOrders) items.set(key, (items.get(key) || 0) + 1);
  $("#planItems").replaceChildren();
  for (const [key, count] of items) {
    const li = document.createElement("li"); li.textContent = `${engine.specs[key].name} +${count} 级`; $("#planItems").append(li);
  }
  const incomeGain = (copy.incomeMultiplier() / engine.incomeMultiplier() - 1) * 100;
  const depthGain = (copy.depthMultiplier() / engine.depthMultiplier() - 1) * 100;
  const leftover = copy.state.credits;
  let nextLine = "";
  const nextKey = copy.manualCandidates().sort((a, b) => copy.costFor(a) - copy.costFor(b))[0];
  if (nextKey) {
    const gap = copy.costFor(nextKey) - leftover;
    nextLine = gap > 0 ? `　本次买不起：**${copy.specs[nextKey].name}**（还差 ${formatNumber(gap)} 矿币）。` : "";
  }
  renderDescription($("#planSummary"), `这一笔会**花掉 ${formatNumber(spent)} 矿币**（现有 ${formatNumber(engine.state.credits)}，买完还剩 ${formatNumber(leftover)}），共 ${pendingOrders.length} 级。\n买完后产能变化：**矿币收益** +${number.format(incomeGain)}%，**挖矿深度** +${number.format(depthGain)}%。${nextLine}\n一键建设用的是**最笨的办法：从最便宜的开始买，买到钱不够为止**——省事，但不是最优解；想要更快就自己挑着买。${resumeMiningAfterDialog ? "\n（看清单的时候时间已经暂停，关掉就继续走，不会白白浪费。）" : ""}`);
  $("#confirmPlan").disabled = !pendingOrders.length; $("#planDialog").showModal();
}
function renderAudit() {
  const days = Number($("#replayDays").value);
  const profiles = ["daily", "absent", "active"].map((key) => [key, runReplay(data, { days, profile: key, route: $("#routeSelect").value })]);
  $("#replayDepthHeading").textContent = "挖穿首星用时";
  $("#replayEraHeading").textContent = `D${days} 时代`;
  const rows = $("#profileRows"); rows.replaceChildren();
  for (const [key, replay] of profiles) {
    const s = replay.engine.state; const tr = document.createElement("tr");
    const first = s.planetHistory?.[0];
    const crackText = first ? `${duration(first.completedMinute)}` : `未挖穿（${percent.format(Math.min(1, s.depth / Number(data.prestige.planetTargetDepth)))}）`;
    const values = [data.strategy.profiles[key].name, s.totalManualLevels, s.totalHelperLevels, s.totalAutoLevels, replay.snapshots.reduce((sum, day) => sum + day.visits, 0), crackText, eraName(replay.engine.currentEra())];
    values.forEach((value, index) => { const cell = document.createElement(index ? "td" : "th"); cell.textContent = value; tr.append(cell); }); rows.append(tr);
  }
  const daily = profiles[0][1]; const active = profiles[2][1]; const max = Math.max(...active.snapshots.map((day) => day.manualLevels));
  $("#auditSummary").replaceChildren();
  [
    ["每日一次 / 手动", daily.snapshots.map((day) => day.manualLevels).join(" · "), `D1 至 D${days}`],
    [`全程托管 / D${days}`, eraName(profiles[1][1].engine.currentEra()), "没有手动购买"],
    ["高频 / 单日最多", `${max} 级`, max > data.rules.manualBurstWarningLevels ? "操作量偏高，需复核" : "本路线未触发操作量预警"],
  ].forEach(([label, value, caption]) => {
    const card = document.createElement("article");
    for (const [tag, text] of [["span", label], ["strong", value], ["small", caption]]) {
      const child = document.createElement(tag); child.textContent = text; card.append(child);
    }
    $("#auditSummary").append(card);
  });
}
function render() { renderStatus(); renderHelper(); renderNext(); renderPrestige(); renderTechTree(); renderMultipliers(); renderFinalReport(); }
function reset() {
  const seed = Number($("#seedInput").value);
  if (!Number.isSafeInteger(seed)) { notice("Seed 必须是安全范围内的整数。"); return; }
  try {
    const current = localStorage.getItem(STORAGE_KEY);
    if (current) localStorage.setItem(`${STORAGE_KEY}-before-reset-${Date.now()}`, current);
  } catch {
    $("#saveNotice").textContent = "重置前备份失败，已取消重置以保护当前进度。";
    return;
  }
  stop(); engine = new S2Engine(data, { seed });
  saveBlocked = false; view = "construction"; save(); render(); notice("新矿井已就绪，笨助手将于次日00:00开始采购。");
}
async function boot() {
  data = await loadGameData(); engine = loadSaved(Number($("#seedInput").value));
  if (sandbox) $("#saveNotice").textContent = ["独立验收矿井", $("#saveNotice").textContent].filter(Boolean).join(" · ");
  document.querySelectorAll("[data-advance]").forEach((button) => button.addEventListener("click", () => advance(Number(button.dataset.advance))));
  $("#toggleButton").addEventListener("click", () => { startMining(); notice("矿井已开工。从现在起时间会一直走下去——挖穿、启程、翻清单都不会让它停。"); });
  $("#helperToggle").addEventListener("change", (event) => {
    engine.setHelperEnabled(event.target.checked); save(); renderHelper();
    notice(engine.state.helperEnabled ? "夜班值班已恢复，将在下一个00:00采购。" : "夜班值班已暂停，已建成的自动线继续生产。");
  });
  $("#autoDepartToggle").addEventListener("change", (event) => {
    engine.setAutoDepart(event.target.checked); save(); renderPrestige();
    const corePurchaseMode = engine.state.coreHelperEnabled
      ? "永久科技由夜班助手和自动线继续购买"
      : "永久科技仍要你亲手买（夜班助手已关）";
    notice(event.target.checked
      ? engine.state.resets > 0 ? `后续星球将自动启程，${corePurchaseMode}。` : "自动启程已预设；首次离开仍需手动确认。"
      : "自动启程已关闭，星球完成后会等待手动确认。");
  });
  $("#coreHelperToggle").addEventListener("change", (event) => {
    try {
      const purchases = engine.setCoreHelperEnabled(event.target.checked);
      save(); render();
      const spent = purchases.reduce((sum, item) => sum + item.cost, 0);
      notice(event.target.checked
        ? purchases.length
          ? `永久科技夜班助手已开启，立即买下 ${purchases.length} 级 · 消耗 ${formatNumber(spent)} 星球核心`
          : "永久科技夜班助手已开启：核心够的时候它会从最便宜的开始买。"
        : "永久科技夜班助手已关闭：没转自动的科技要你亲手买了。");
    } catch (error) {
      renderPrestige();
      notice(`夜班助手设置失败：${error.message}`);
    }
  });
  $("#departButton").addEventListener("click", () => {
    const result = engine.departPlanet();
    if (!result.ok) {
      notice(result.reason === "unfinished"
        ? "当前星球尚未达到目标深度。"
        : result.reason === "galaxy" ? "银河目标已经完成，不能再次启程。" : "现在还不能前往下一颗星球。");
      render();
      return;
    }
    view = "construction"; startMining(); save(); render();
    showToast(`🚀 启程！现在是第 ${currentPlanet()} 颗星球`);
    notice(`已启程前往第 ${currentPlanet()} 颗星球 · 本地建设已重置，星球核心与永久科技完整保留 · 矿井继续运转`);
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => { view = button.dataset.view; renderTechTree(); });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const tabs = [...document.querySelectorAll("[data-view]")];
      const next = tabs[(tabs.indexOf(button) + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      next.click(); next.focus();
    });
  });
  $("#planButton").addEventListener("click", previewPlan);
  $("#confirmPlan").addEventListener("click", () => { buy(pendingOrders); pendingOrders = []; $("#planDialog").close(); });
  $("#planDialog").addEventListener("close", maybeResumeMining);
  $("#resetButton").addEventListener("click", () => { pauseForDialog(); $("#resetDialog").showModal(); });
  $("#resetDialog").addEventListener("close", maybeResumeMining);
  $("#confirmReset").addEventListener("click", () => { reset(); $("#resetDialog").close(); });
  $("#replayButton").addEventListener("click", renderAudit);
  render(); renderAudit(); save();
  // 刷新页面不该让矿井停产：已经开过工的存档自动继续运转。
  if (engine.state.minute > 0 && !engine.galaxyComplete()) startMining();
  exposeDebugApi();
}
// 这个 demo 的主要读者是反复试玩它的 AI。给一个稳定的机读接口，
// 省得每轮都去截图 + 猜 DOM 结构。
function exposeDebugApi() {
  window.s2 = {
    get engine() { return engine; },
    state() {
      const s = engine.state; const sector = engine.sectorProgress();
      return {
        time: clock(s.minute), day: Math.floor(s.minute / 1440) + 1, minute: s.minute,
        credits: s.credits, depth: s.depth, era: eraName(engine.currentEra()),
        planet: currentPlanet(), completedPlanets: s.completedPlanets, cores: s.cores,
        prestigeSpeed: engine.prestigeSpeed(), running: timer !== null,
        planetComplete: s.planetComplete, galaxyComplete: engine.galaxyComplete(),
        sector: sector && { index: sector.index + 1, name: sector.sector.name, done: sector.done, target: sector.target, ratio: sector.ratio },
        counts: { manual: s.totalManualLevels, helper: s.totalHelperLevels, auto: s.totalAutoLevels, commands: s.totalManualCommands },
        autoDepart: s.autoDepart, manualDepartLeft: Math.max(0, engine.manualDepartureQuota() - s.resets),
        coreHelperEnabled: s.coreHelperEnabled, helperEnabled: s.helperEnabled,
        commissionedTechs: s.coreAutoUnlocked.length, coreCommissionLevels: engine.coreCommissionLevels,
        unlockedTechs: engine.unlockedCoreKeys().length,
        buyableTechs: Object.values(engine.coreSpecs).filter((spec) => engine.coreAvailable(spec.key) && engine.coreCost(spec.key) <= s.cores)
          .map((spec) => ({ key: spec.key, name: spec.name, cost: engine.coreCost(spec.key) })),
        nextUpgrade: $("#nextName").textContent, notice: $("#actionNotice").textContent,
      };
    },
    start: () => startMining(),
    plan: () => { previewPlan(); $("#confirmPlan").click(); return window.s2.state(); },
    depart: () => { $("#departButton").click(); return window.s2.state(); },
    buyTech: (key) => { buyCore(key); return window.s2.state(); },
    setCoreHelper: (on) => { engine.setCoreHelperEnabled(Boolean(on)); save(); render(); return window.s2.state(); },
  };
}
boot().catch((error) => {
  const message = document.createElement("pre"); message.className = "fatal";
  message.textContent = `矿井启动失败\n${error.message}`; document.body.replaceChildren(message);
});
