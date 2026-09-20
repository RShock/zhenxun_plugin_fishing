// Offline authoring tool. Runtime prices never depend on a player's login or income.
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { S2Engine, runReplay } from "../../../../web/static/s2-vnext/engine.js";

const path = fileURLToPath(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url));
const data = JSON.parse(fs.readFileSync(path, "utf8"));
const schedule = [
  [12, "grid_resonance"], [12, "seismic_echo"],
  [13, "induction_ledger"], [13, "capacitor_bank"], [14, "sorting_optics"],
  [15, "pressure_converter"], [16, "mesh_topology"], [16, "ceramic_bearings"],
  [17, "thermal_recovery"], [18, "craft_diversity"], [18, "support_lattice"],
  [19, "cascade_bus"], [20, "closed_loop_cooling"], [20, "autonomous_survey"],
  [21, "pressure_accumulator"], [22, "precision_matrix"], [23, "distance_fold"],
  [23, "phase_anchor"], [24, "gravity_lens"], [25, "singularity_crew"],
  [26, "quantum_fault"], [27, "vacuum_bus"], [28, "quantum_sorter"],
  [29, "tidal_bore"], [30, "stellar_sync"],
];
const byKey = Object.fromEntries(data.upgrades.map((spec) => [spec.key, spec]));
const round = (value) => Number(value.toPrecision(3));
for (const [, key] of schedule) {
  Object.assign(byKey[key], { status: "active", unlockDepth: 1e250, baseCost: 1e250 });
}
data.eras.find((era) => era.key === "modern").status = "d15-d21";
data.eras.find((era) => era.key === "future").status = "d22-d30";
data.eras.find((era) => era.key === "modern").unlockDepth = 1e250;
data.eras.find((era) => era.key === "future").unlockDepth = 1e250;
data.eras.find((era) => era.key === "planetary").unlockDepth = 1e250;
data.strategy.priority = [
  ...data.strategy.priority.filter((key) => !schedule.some(([, later]) => key === later)),
  ...schedule.map(([, key]) => key),
];
for (const [day, key] of schedule) {
  const engine = new S2Engine(data, { seed: 42 });
  const target = (day - 1) * 1440 + 780;
  while (engine.state.minute < target) {
    engine.mineBlock();
    if (engine.state.minute % 1440 === 1200) engine.strategyVisit();
  }
  const spec = byKey[key];
  const sameDay = schedule.filter(([other]) => other === day).length;
  const commissioningCost = engine.incomeMultiplier() * data.rules.baseCreditsPerMinute * 720 / sameDay;
  spec.unlockDepth = round(engine.state.depth);
  spec.baseCost = round(commissioningCost / (1 + spec.costGrowth + spec.costGrowth ** 2));
  if (key === "pressure_converter" || key === "precision_matrix") {
    data.eras.find((era) => era.key === spec.era).unlockDepth = spec.unlockDepth;
  }
  console.log(`D${day} ${key}: depth=${spec.unlockDepth} cost=${spec.baseCost}`);
}
const final = runReplay(data, { days: 30 });
// This is an authoring horizon marker, not the price or depth of prestige.
data.rules.developmentTargetDepth = round(final.engine.state.depth * 1000);
data.eras.find((era) => era.key === "planetary").unlockDepth = data.rules.developmentTargetDepth;
for (const profile of ["daily", "absent", "active"]) {
  const replay = runReplay(data, { days: 30, profile });
  console.log(profile, JSON.stringify(replay.snapshots.filter((day) => day.day >= 11).map((day) => ({
    day: day.day, depth: round(day.depth), manual: day.manualLevels,
    helper: day.helperLevels, auto: day.autoLevels, era: day.currentEra,
  }))));
}
if (process.argv.includes("--write")) {
  fs.writeFileSync(path, `${JSON.stringify(data, null, 2)}\n`);
  console.log("Updated the shared game_data.json. Run independent audits before accepting it.");
} else console.log("Preview only. Pass --write to update the shared data.");
