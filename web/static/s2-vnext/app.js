import { S2Engine, loadGameData, runReplay } from "./engine.js?v=3-thirty-1";

const sandbox = new URLSearchParams(location.search).get("sandbox") === "1";
const STORAGE_KEY = `s2-vnext-save-v3-helper${sandbox ? "-sandbox-thirty" : ""}`;
const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 2 });
const $ = (selector) => document.querySelector(selector);
const formatNumber = (value) => Math.abs(value) >= 1e15 ? value.toExponential(2) : Math.abs(value) >= 1e7 ? compact.format(value) : number.format(value);
const formatMultiplier = (value) => `×${formatNumber(value)}`;
let data; let engine; let timer = null; let view = "construction"; let pendingOrders = []; let saveBlocked = false;
const eraName = (key) => data.eras.find((item) => item.key === key)?.name || key;
const clock = (minute) => `D${Math.floor(minute / 1440) + 1} ${String(Math.floor(minute % 1440 / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
const duration = (minutes) => minutes < 60 ? `${Math.ceil(minutes)}分钟` : `${number.format(minutes / 60)}小时`;
const notice = (text) => { $("#actionNotice").textContent = text; };

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
          $("#saveNotice").textContent = "已接续三十天矿井，更新前的进度已备份。";
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
  const before = { credits: engine.state.credits, depth: engine.state.depth, auto: engine.state.totalAutoLevels, helper: engine.state.totalHelperLevels };
  engine.mineBlock(minutes);
  save(); render();
  notice(`已过${duration(minutes)} · 深度 +${formatNumber(engine.state.depth - before.depth)} · 助手建设 ${engine.state.totalHelperLevels - before.helper} 级 · 自动采购 ${engine.state.totalAutoLevels - before.auto} 级 · 矿币净变动 ${formatNumber(engine.state.credits - before.credits)}`);
}
function lockedReason(key) {
  const spec = engine.specs[key];
  if (spec.status !== "active") return "尚未开放";
  if (engine.level(key) >= spec.maxLevel) return "本时代已满级";
  if (engine.state.autoUnlocked.includes(key)) return "每小时参与自动采购";
  if (!engine.eraUnlocked(spec.era)) {
    const era = engine.eraByKey[spec.era];
    const previous = engine.eraSequence[engine.eraSequence.indexOf(spec.era) - 1];
    return `${era.name}：深度 ${formatNumber(era.unlockDepth)}，${eraName(previous)}自动线 ${engine.eraAutomationCount(previous)}/${era.previousEraAutomations}`;
  }
  if (engine.state.depth < spec.unlockDepth) return `深度 ${formatNumber(engine.state.depth)} / ${formatNumber(spec.unlockDepth)}`;
  const missing = spec.prerequisites.filter((key) => engine.level(key) < 1);
  if (missing.length) return `前置工程：${missing.map((key) => engine.specs[key].name).join("、")}`;
  if (engine.state.credits < engine.costFor(key)) return `还差 ${formatNumber(engine.costFor(key) - engine.state.credits)} 矿币`;
  return "";
}
function renderStatus() {
  const s = engine.state;
  $("#timeValue").textContent = clock(s.minute); $("#seedValue").textContent = `seed ${s.seed}`;
  $("#creditsValue").textContent = formatNumber(s.credits); $("#depthValue").textContent = formatNumber(s.depth);
  $("#incomeRate").textContent = `+${formatNumber(data.rules.baseCreditsPerMinute * engine.incomeMultiplier())} / 分钟`;
  $("#depthRate").textContent = `+${formatNumber(data.rules.baseDepthPerMinute * engine.depthMultiplier())} / 分钟`;
  $("#eraValue").textContent = eraName(engine.currentEra());
  $("#automationValue").textContent = `${s.autoUnlocked.length} 条自动线`;
  $("#totalBuiltValue").textContent = s.totalManualLevels + s.totalHelperLevels + s.totalAutoLevels;
  $("#purchaseCounts").textContent = `手动 ${s.totalManualLevels} · 助手 ${s.totalHelperLevels} · 自动 ${s.totalAutoLevels}`;
  $("#sceneEra").textContent = eraName(engine.currentEra());
  $("#sceneStatus").textContent = `${s.autoUnlocked.length} 条自动线运转中`;
  $("#toggleButton").textContent = timer ? "暂停推进" : "连续挖矿";
  $("#planButton").disabled = !engine.chooseUpgrade("balanced");
}
function renderHelper() {
  const s = engine.state; const report = s.lastHelperReport;
  $("#helperToggle").checked = s.helperEnabled;
  $("#helperNext").textContent = s.helperEnabled ? clock(s.nextHelperMinute) : "已暂停值班";
  $("#helperCountdown").textContent = s.helperEnabled ? `还有${duration(s.nextHelperMinute - s.minute)} · 低价优先` : "装备自动采购继续运行";
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
  const candidates = engine.manualCandidates().sort((a, b) => engine.costFor(a) - engine.costFor(b));
  const next = candidates[0] || data.upgrades.filter((spec) => spec.status === "active" && !engine.state.autoUnlocked.includes(spec.key))
    .sort((a, b) => a.unlockDepth - b.unlockDepth)[0]?.key;
  if (!next) {
    $("#nextName").textContent = "本段工程已全部自动化";
    $("#nextReason").textContent = "矿井继续生产，后续星层尚未开放。";
    $("#nextProgress").value = 1; $("#nextProgressText").textContent = "本轮三十天工程已交付"; $("#nextEta").textContent = "";
    return;
  }
  const spec = engine.specs[next]; let current; let target; let rate; let unit;
  $("#nextName").textContent = spec.name; $("#nextReason").textContent = lockedReason(next) || "矿币充足，可以开工";
  if (engine.available(next)) {
    current = engine.state.credits; target = engine.costFor(next);
    rate = data.rules.baseCreditsPerMinute * engine.incomeMultiplier(); unit = "矿币";
  } else {
    current = engine.state.depth; target = Math.max(spec.unlockDepth, engine.eraByKey[spec.era].unlockDepth);
    rate = data.rules.baseDepthPerMinute * engine.depthMultiplier(); unit = "深度";
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
  const active = data.upgrades.filter((spec) => spec.status === "active");
  const groups = {
    construction: active.filter((spec) => engine.available(spec.key)),
    automated: active.filter((spec) => engine.state.autoUnlocked.includes(spec.key)),
    frontier: active.filter((spec) => !engine.available(spec.key) && !engine.state.autoUnlocked.includes(spec.key)),
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
      card.classList.toggle("automated", auto); card.classList.toggle("locked", view === "frontier");
      card.querySelector("h3").textContent = spec.name; card.querySelector(".description").textContent = spec.description;
      card.querySelector(".level-chip").textContent = `Lv.${engine.level(spec.key)} / ${spec.maxLevel}`;
      card.querySelector(".region").textContent = data.multiplierRegions.find((item) => item.key === spec.region)?.name || spec.region;
      card.querySelector(".cost").textContent = engine.level(spec.key) >= spec.maxLevel ? "已满级" : `${formatNumber(engine.costFor(spec.key))} 矿币`;
      card.querySelector(".progress-label").textContent = auto ? "已自动化" : `调试 ${commissioned} / ${spec.manualTarget}`;
      [...card.querySelectorAll(".manual-progress i")].forEach((dot, index) => dot.classList.toggle("filled", index < commissioned));
      const reason = lockedReason(spec.key);
      const upgrade = card.querySelector(".upgrade-button"); upgrade.disabled = Boolean(reason);
      upgrade.addEventListener("click", () => buy([[spec.key, 1]]));
      const complete = card.querySelector(".commission-button"); const remaining = spec.manualTarget - commissioned;
      const fullCost = Array.from({ length: remaining }, (_, i) => engine.costFor(spec.key, engine.level(spec.key) + i)).reduce((sum, cost) => sum + cost, 0);
      complete.disabled = Boolean(reason) || engine.state.credits < fullCost;
      complete.title = `剩余 ${remaining} 级，共 ${formatNumber(fullCost)} 矿币`;
      complete.addEventListener("click", () => buy([[spec.key, remaining]]));
      card.querySelector(".lock-reason").textContent = reason || `再建设 ${remaining} 级后自动采购`;
      grid.append(card);
    }
    group.append(grid); root.append(group);
  }
  if (!root.children.length) {
    const p = document.createElement("p"); p.className = "empty";
    p.textContent = view === "construction"
      ? groups.frontier.length ? "当前装备已交给自动生产线。矿井正在接近下一项工程。" : "本段工程均已自动化，矿井继续生产。"
      : view === "automated" ? "尚无自动生产线。" : "当前阶段的工程均已发现。";
    root.append(p);
  }
}
function renderMultipliers() {
  const root = $("#multiplierList"); root.replaceChildren();
  Object.entries(engine.multiplierBreakdown()).filter(([, value]) => value > 1.000001).forEach(([key, value]) => {
    const region = data.multiplierRegions.find((item) => item.key === key || item.key === key.replace("_", ""));
    const row = document.createElement("div"); const label = document.createElement("span"); const count = document.createElement("b");
    label.textContent = key === "critical" ? "暴击期望" : region?.name || key; count.textContent = formatMultiplier(value); row.append(label, count); root.append(row);
  });
  $("#incomeMultiplier").textContent = formatMultiplier(engine.incomeMultiplier());
  $("#depthMultiplier").textContent = formatMultiplier(engine.depthMultiplier());
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
  $("#planSummary").textContent = `${pendingOrders.length} 级工程，共 ${formatNumber(spent)} 矿币；剩余 ${formatNumber(copy.state.credits)} 矿币。当前产能：收入 +${number.format(incomeGain)}%，钻进 +${number.format(depthGain)}%。`;
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
function render() { renderStatus(); renderHelper(); renderNext(); renderTechTree(); renderMultipliers(); }
function reset() {
  const seed = Number($("#seedInput").value);
  if (!Number.isSafeInteger(seed)) { notice("Seed 必须是安全范围内的整数。"); return; }
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
