import { S2Engine, loadGameData, runReplay } from "./engine.js?v=3-prestige-1";
import { renderDescription } from "./description.js?v=3-readable-tech-1";

const sandbox = new URLSearchParams(location.search).get("sandbox") === "1";
const STORAGE_KEY = `s2-vnext-save-v3-helper${sandbox ? "-sandbox-thirty" : ""}`;
const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 2 });
const percent = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 2 });
const coefficient = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 6 });
const $ = (selector) => document.querySelector(selector);
const formatNumber = (value) => Math.abs(value) >= 1e15 ? value.toExponential(2) : Math.abs(value) >= 1e7 ? compact.format(value) : number.format(value);
const formatMultiplier = (value) => `×${formatNumber(value)}`;
let data; let engine; let timer = null; let view = "construction"; let pendingOrders = []; let saveBlocked = false;
const eraName = (key) => data.eras.find((item) => item.key === key)?.name || key;
const clock = (minute) => `D${Math.floor(minute / 1440) + 1} ${String(Math.floor(minute % 1440 / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
const duration = (minutes) => {
  const value = Math.max(0, minutes);
  if (value < 60) return `${Math.ceil(value)}分钟`;
  if (value < 1440) return `${number.format(value / 60)}小时`;
  const totalHours = Math.ceil(value / 60);
  const days = Math.floor(totalHours / 24); const hours = totalHours % 24;
  return hours ? `${days}天${hours}小时` : `${days}天`;
};
const notice = (text) => { $("#actionNotice").textContent = text; };
const activeSpecs = () => data.upgrades.filter((spec) => spec.status === "active");
const manualTarget = (key) => Math.max(0, Number(engine.manualTarget(key)));
const currentPlanet = () => Number(engine.state.resets || 0) + 1;

function loadSaved(seed) {
  let raw; let legacy;
  try { raw = localStorage.getItem(STORAGE_KEY); legacy = localStorage.getItem("s2-vnext-save-v2"); }
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
  } else if (legacy) {
    $("#saveNotice").textContent = "已开启独立的助手版矿井；原版试玩存档仍保留。";
  }
  return new S2Engine(data, { seed });
}
function save() {
  if (saveBlocked) return;
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(engine.snapshot())); }
  catch { $("#saveNotice").textContent = "浏览器存储不可用，本次进度未保存。"; }
}
function stop() { clearInterval(timer); timer = null; }
function advance(minutes) {
  const before = {
    credits: engine.state.credits, depth: engine.state.depth, auto: engine.state.totalAutoLevels,
    helper: engine.state.totalHelperLevels, completed: engine.state.completedPlanets, resets: engine.state.resets,
  };
  engine.mineBlock(minutes);
  save(); render();
  const completed = engine.state.completedPlanets - before.completed;
  const departed = engine.state.resets - before.resets;
  const parts = [`已过${duration(minutes)}`];
  if (completed > 0) parts.push(`挖穿 ${completed} 颗星球`);
  if (departed > 0) parts.push(`自动启程 ${departed} 次`);
  if (departed === 0) {
    parts.push(`深度 +${formatNumber(Math.max(0, engine.state.depth - before.depth))}`);
    const creditDelta = engine.state.credits - before.credits;
    parts.push(`矿币净变动 ${creditDelta >= 0 ? "+" : ""}${formatNumber(creditDelta)}`);
  } else {
    parts.push(`现为第 ${currentPlanet()} 颗星球`);
  }
  parts.push(`助手建设 ${engine.state.totalHelperLevels - before.helper} 级`);
  parts.push(`自动采购 ${engine.state.totalAutoLevels - before.auto} 级`);
  if (engine.state.planetComplete && departed === 0) parts.push("生产已停止，请手动启程");
  notice(parts.join(" · "));
}
function lockedReason(key) {
  const spec = engine.specs[key];
  const target = manualTarget(key);
  if (engine.state.planetComplete) return "当前星球已挖穿，离开后可继续建设";
  if (spec.status !== "active") return "尚未开放";
  if (engine.level(key) >= spec.maxLevel) return "本代设备已满级";
  if (engine.state.autoUnlocked.includes(key)) {
    return engine.state.resets > 0 ? "每10分钟参与自动采购，预算随永久速度提升" : "每小时参与自动采购";
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
      ? "已解锁；下次10分钟结算会尝试首次付费，成功后加入自动线"
      : `已解锁；首次自动采购还差 ${formatNumber(cost - engine.state.credits)} 矿币`;
  }
  if (engine.state.credits < engine.costFor(key)) return `还差 ${formatNumber(engine.costFor(key) - engine.state.credits)} 矿币`;
  return "";
}
function renderStatus() {
  const s = engine.state;
  $("#timeValue").textContent = clock(s.minute); $("#seedValue").textContent = `seed ${s.seed}`;
  $("#stationPlanet").textContent = `第 ${currentPlanet()} 颗星球`;
  $("#creditsValue").textContent = formatNumber(s.credits); $("#depthValue").textContent = formatNumber(s.depth);
  $("#incomeRate").textContent = s.planetComplete ? "生产已停止，等待离开星球" : `矿币收益 +${formatNumber(data.rules.baseCreditsPerMinute * engine.incomeMultiplier())} / 分钟`;
  $("#depthRate").textContent = s.planetComplete ? "深度停止增长" : `+${formatNumber(data.rules.baseDepthPerMinute * engine.depthMultiplier())} / 分钟`;
  $("#eraValue").textContent = eraName(engine.currentEra());
  $("#automationValue").textContent = `${s.autoUnlocked.length} 条自动线`;
  $("#totalBuiltValue").textContent = s.totalManualLevels + s.totalHelperLevels + s.totalAutoLevels;
  $("#purchaseCounts").textContent = `手动 ${s.totalManualLevels} · 助手 ${s.totalHelperLevels} · 自动 ${s.totalAutoLevels}`;
  $("#sceneEra").textContent = eraName(engine.currentEra());
  $("#sceneStatus").textContent = s.planetComplete ? "星球已挖穿 · 全部生产停止" : `${s.autoUnlocked.length} 条自动线运转中`;
  if (s.planetComplete && timer) stop();
  $("#toggleButton").textContent = timer ? "暂停推进" : "连续挖矿";
  $("#toggleButton").disabled = s.planetComplete;
  document.querySelectorAll("[data-advance]").forEach((button) => { button.disabled = s.planetComplete; });
  $("#planButton").disabled = s.planetComplete || !engine.chooseUpgrade("balanced");
}
function renderHelper() {
  const s = engine.state; const report = s.lastHelperReport;
  $("#helperToggle").checked = s.helperEnabled;
  $("#helperNext").textContent = s.planetComplete ? "等待下一颗星球" : s.helperEnabled ? clock(s.nextHelperMinute) : "已暂停值班";
  $("#helperCountdown").textContent = s.planetComplete ? "本星球生产与采购均已停止" : s.helperEnabled ? `还有${duration(s.nextHelperMinute - s.minute)} · 低价优先` : "装备自动采购继续运行";
  $("#helperResult").textContent = report ? `建设 ${report.levels} 级` : "等待第一班";
  $("#helperSpent").textContent = report ? `${clock(report.minute)} · 花费 ${formatNumber(report.spent)} 矿币` : "每日00:00采购";
  const root = $("#helperItems"); root.replaceChildren();
  const items = new Map();
  for (const item of report?.items || []) items.set(item.key, (items.get(item.key) || 0) + 1);
  for (const [key, levels] of items) {
    const span = document.createElement("span"); span.textContent = `${engine.specs[key].name} +${levels}`; root.append(span);
  }
  if (!items.size) root.textContent = report ? "本班没有新增建设。" : "值班记录尚为空。";
}
function renderNext() {
  if (engine.state.planetComplete) {
    $("#nextName").textContent = `第 ${currentPlanet()} 颗星球已挖穿`;
    renderDescription($("#nextReason"), "星球核心奖励已结算，本星球不再生产。请在**行星航程**中确认重置内容并启程。");
    $("#nextProgress").value = 1;
    $("#nextProgressText").textContent = `目标深度 ${formatNumber(data.prestige.planetTargetDepth)}`;
    $("#nextEta").textContent = "等待离开";
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
    return;
  }
  const spec = engine.specs[next]; let current; let target; let rate; let unit;
  $("#nextName").textContent = spec.name; renderDescription($("#nextReason"), lockedReason(next) || "矿币充足，可以开工");
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
}
function buy(orders) {
  const result = engine.upgradeCommand(orders);
  if (result.ok) {
    save(); render();
    const spent = result.purchases.reduce((sum, item) => sum + item.cost, 0);
    notice(`完成 ${result.purchases.length} 级建设 · 花费 ${formatNumber(spent)} 矿币${result.reason ? " · 余下工程暂未满足条件" : ""}`);
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
      card.querySelector("h3").textContent = spec.name;
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
      card.querySelector(".progress-label").textContent = auto ? "已自动化" : target === 0 ? "重复星球自动建设" : `调试 ${commissioned} / ${target}`;
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
      const complete = card.querySelector(".commission-button"); const remaining = Math.max(0, target - commissioned);
      const fullCost = Array.from({ length: remaining }, (_, i) => engine.costFor(spec.key, engine.level(spec.key) + i)).reduce((sum, cost) => sum + cost, 0);
      complete.disabled = remaining === 0 || Boolean(reason) || engine.state.credits < fullCost;
      complete.title = `剩余 ${remaining} 级，共 ${formatNumber(fullCost)} 矿币`;
      complete.addEventListener("click", () => buy([[spec.key, remaining]]));
      renderDescription(card.querySelector(".lock-reason"), reason || `再建设 ${remaining} 级后自动采购`);
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
    const prestigeNames = { prestige: "永久轮回速度", stellar_relay: "联合勘探" };
    label.textContent = key === "critical" ? "暴击期望" : prestigeNames[key] || region?.name || key; count.textContent = formatMultiplier(value); row.append(label, count); root.append(row);
  });
  $("#incomeMultiplier").textContent = formatMultiplier(engine.incomeMultiplier());
  $("#depthMultiplier").textContent = formatMultiplier(engine.depthMultiplier());
}
function thresholdSummary(source = engine) {
  const targets = activeSpecs().map((spec) => Math.max(0, Number(source.manualTarget(spec.key))));
  const low = Math.min(...targets); const high = Math.max(...targets);
  if (high === 0) return "0级（全自动）";
  return low === high ? `${high}级` : `${low}–${high}级`;
}
function departurePreview() {
  if (!engine.state.planetComplete) return null;
  const copy = new S2Engine(data, { state: engine.snapshot() });
  const result = copy.departPlanet();
  return result.ok ? { speed: copy.prestigeSpeed(), threshold: thresholdSummary(copy) } : null;
}
function coreGroup(spec) {
  if (Number(spec.unlockResets) <= 1) return ["planet", "行星技术"];
  if (Number(spec.unlockResets) <= 5) return ["star", "恒星系技术"];
  return ["galaxy", "银河技术"];
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
  notice(`永久科技升级至 Lv.${result.level} · 消耗 ${formatNumber(result.cost)} 星球核心`);
}
function renderCoreShop() {
  const root = $("#coreShop"); root.replaceChildren();
  const upgrades = data.prestige?.upgrades || [];
  const grouped = new Map([["planet", []], ["star", []], ["galaxy", []]]);
  const labels = new Map();
  for (const spec of upgrades) {
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
      const top = document.createElement("div"); top.className = "tech-top";
      const gate = document.createElement("span"); gate.textContent = `完成 ${spec.unlockResets} 颗星球`;
      const levelChip = document.createElement("span"); levelChip.className = "level-chip"; levelChip.textContent = `Lv.${level} / ${spec.maxLevel}`;
      top.append(gate, levelChip);
      const name = document.createElement("h3"); name.textContent = spec.name;
      const description = document.createElement("p"); description.className = "description";
      renderDescription(description, spec.description);
      const permanent = document.createElement("p"); permanent.className = "permanent-note";
      permanent.textContent = level > 0 ? `永久生效 ${level} 级` : "永久效果尚未启用";
      const actions = document.createElement("div"); actions.className = "core-actions";
      const status = document.createElement("small"); status.textContent = reason || `可用星球核心 ${formatNumber(engine.state.cores)}`;
      const button = document.createElement("button"); button.className = "primary";
      button.textContent = level >= spec.maxLevel ? "已满级" : `购买 · ${formatNumber(cost)} 星球核心`;
      button.disabled = !available || engine.state.cores < cost; button.addEventListener("click", () => buyCore(spec.key));
      actions.append(status, button); card.append(top, name, description, permanent, actions); grid.append(card);
    }
    group.append(grid); root.append(group);
  }
  if (!upgrades.length) {
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
function renderPrestige() {
  const s = engine.state;
  const target = Number(data.prestige.planetTargetDepth);
  const completed = s.planetComplete
    ? [...(s.planetHistory || [])].reverse().find((item) => item.planet === currentPlanet())
    : null;
  const elapsed = completed ? Number(completed.minutes) : Math.max(0, s.minute - s.planetStartedMinute);
  const progress = target > 0 ? Math.min(1, s.depth / target) : 0;
  $("#planetTitle").textContent = `第 ${currentPlanet()} 颗星球`;
  $("#planetState").textContent = s.planetComplete ? "已挖穿 · 等待启程" : "开采进行中";
  $("#planetProgress").value = progress;
  $("#planetProgressText").textContent = `深度 ${formatNumber(Math.min(s.depth, target))} / ${formatNumber(target)}`;
  $("#planetElapsed").textContent = `本星球 ${duration(elapsed)}`;
  $("#coresValue").textContent = formatNumber(s.cores);
  $("#resetsValue").textContent = formatNumber(s.resets);
  $("#completedValue").textContent = formatNumber(s.completedPlanets);
  $("#prestigeSpeed").textContent = formatMultiplier(engine.prestigeSpeed());
  $("#prestigeThreshold").textContent = thresholdSummary();
  const prestigeUnlocked = s.completedPlanets > 0;
  $("#prestigeLockedReward").hidden = prestigeUnlocked;
  $("#departurePanel").hidden = !prestigeUnlocked;
  $("#prestigeContent").hidden = !prestigeUnlocked;
  const stellarRelay = Number(engine.multiplierBreakdown().stellar_relay || 1);
  const speedCap = Number(data.prestige?.speedDoublingCap || 0);
  renderDescription($("#permanentSummary"), `**轮回速度** ${formatMultiplier(engine.prestigeSpeed())} · **联合勘探** ${formatMultiplier(stellarRelay)}${speedCap ? ` · 前${speedCap}次转生逐次翻倍，之后继续增长` : ""}`);
  const allMaxed = s.allMaxedMinute === null ? null : Math.max(0, Number(s.allMaxedMinute) - Number(s.planetStartedMinute));
  $("#allMaxedStatus").textContent = allMaxed === null
    ? engine.allLocalMaxed() ? "设备已满级，旧进度未记录满级时刻" : "设备尚未全部满级"
    : `全部满级于本轮 ${duration(allMaxed)}`;

  const announcement = $("#completionAnnouncement");
  announcement.hidden = !s.planetComplete;
  if (s.planetComplete) {
    renderDescription(announcement, `第 ${currentPlanet()} 颗星球已经挖穿，${completed ? `**${formatNumber(completed.reward)} 星球核心**已发放一次` : "**星球核心奖励**已发放一次"}。本星球生产已停止。`);
  }

  const preview = departurePreview();
  $("#departButton").hidden = !s.planetComplete;
  $("#departButton").disabled = !preview;
  if (preview) {
    renderDescription($("#departureDescription"), `启程会重置**矿币、深度、全部设备和全部本地科技等级**；保留**星球核心、永久科技、累计建设等级与命令数**。下一颗星球基础开采速度 ${formatMultiplier(preview.speed)}，每项设备调试 ${preview.threshold} 后进入自动线。`);
  } else {
    renderDescription($("#departureDescription"), `挖穿目标深度后可前往下一颗星球。启程会重置**全部设备和全部本地科技等级**；**星球核心、永久科技和全部累计统计**会保留。当前永久基础速度 ${formatMultiplier(engine.prestigeSpeed())}，本星每项设备调试 ${thresholdSummary()}。`);
  }
  $("#autoDepartToggle").checked = s.autoDepart;
  $("#autoDepartHint").textContent = s.resets > 0
    ? s.autoDepart ? "后续星球完成时自动启程；星球核心仍由你手动消费。" : "后续星球完成后会停下，等待手动启程。"
    : "首次离开必须手动确认；此设置从下一颗星球起生效。";
  renderCoreShop(); renderHistory();
}
function previewPlan() {
  stop(); renderStatus();
  const copy = new S2Engine(data, { state: engine.snapshot() });
  pendingOrders = [];
  while (pendingOrders.length < data.rules.batchCommandMaxLevels) {
    const key = copy.chooseUpgrade($("#routeSelect").value);
    if (!key) break;
    copy.upgradeCommand([[key, 1]]); pendingOrders.push([key, 1]);
  }
  const spent = engine.state.credits - copy.state.credits; const items = new Map();
  for (const [key] of pendingOrders) items.set(key, (items.get(key) || 0) + 1);
  $("#planItems").replaceChildren();
  for (const [key, count] of items) {
    const li = document.createElement("li"); li.textContent = `${engine.specs[key].name} +${count} 级`; $("#planItems").append(li);
  }
  const incomeGain = (copy.incomeMultiplier() / engine.incomeMultiplier() - 1) * 100;
  const depthGain = (copy.depthMultiplier() / engine.depthMultiplier() - 1) * 100;
  renderDescription($("#planSummary"), `${pendingOrders.length} 级工程，共 ${formatNumber(spent)} 矿币；剩余 ${formatNumber(copy.state.credits)} 矿币。当前产能：**矿币收益** +${number.format(incomeGain)}%，**挖矿深度** +${number.format(depthGain)}%。`);
  $("#confirmPlan").disabled = !pendingOrders.length; $("#planDialog").showModal();
}
function renderAudit() {
  const days = Number($("#replayDays").value);
  const profiles = ["daily", "absent", "active"].map((key) => [key, runReplay(data, { days, profile: key, route: $("#routeSelect").value })]);
  $("#replayDepthHeading").textContent = `D${days} 深度`;
  $("#replayEraHeading").textContent = `D${days} 时代`;
  const rows = $("#profileRows"); rows.replaceChildren();
  for (const [key, replay] of profiles) {
    const s = replay.engine.state; const tr = document.createElement("tr");
    const values = [data.strategy.profiles[key].name, s.totalManualLevels, s.totalHelperLevels, s.totalAutoLevels, replay.snapshots.reduce((sum, day) => sum + day.visits, 0), formatNumber(s.depth), eraName(replay.engine.currentEra())];
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
function render() { renderStatus(); renderHelper(); renderNext(); renderPrestige(); renderTechTree(); renderMultipliers(); }
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
  $("#toggleButton").addEventListener("click", () => {
    if (timer) stop(); else timer = setInterval(() => advance(10), 550);
    renderStatus();
  });
  $("#helperToggle").addEventListener("change", (event) => {
    engine.setHelperEnabled(event.target.checked); save(); renderHelper();
    notice(engine.state.helperEnabled ? "夜班值班已恢复，将在下一个00:00采购。" : "夜班值班已暂停，已建成的自动线继续生产。");
  });
  $("#autoDepartToggle").addEventListener("change", (event) => {
    engine.setAutoDepart(event.target.checked); save(); renderPrestige();
    notice(event.target.checked
      ? engine.state.resets > 0 ? "后续星球将自动启程，永久科技仍保持手动购买。" : "自动启程已预设；首次离开仍需手动确认。"
      : "自动启程已关闭，星球完成后会等待手动确认。");
  });
  $("#departButton").addEventListener("click", () => {
    const result = engine.departPlanet();
    if (!result.ok) {
      notice(result.reason === "unfinished" ? "当前星球尚未达到目标深度。" : "现在还不能前往下一颗星球。");
      render();
      return;
    }
    stop(); view = "construction"; save(); render();
    notice(`已启程前往第 ${currentPlanet()} 颗星球 · 本地建设已重置，星球核心与永久科技完整保留`);
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
  $("#resetButton").addEventListener("click", () => { stop(); renderStatus(); $("#resetDialog").showModal(); });
  $("#confirmReset").addEventListener("click", () => { reset(); $("#resetDialog").close(); });
  $("#replayButton").addEventListener("click", renderAudit);
  render(); renderAudit(); save();
}
boot().catch((error) => {
  const message = document.createElement("pre"); message.className = "fatal";
  message.textContent = `矿井启动失败\n${error.message}`; document.body.replaceChildren(message);
});
