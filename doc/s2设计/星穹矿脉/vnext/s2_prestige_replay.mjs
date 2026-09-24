import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { S2Engine } from "../../../../web/static/s2-vnext/engine.js";

export function replayPrestige(data, { seed = 42, profile = "daily", planets = 12, days = 300, coreRoute = "balanced" } = {}) {
  if (!["daily", "absent"].includes(profile) || !["balanced", "speed", "none"].includes(coreRoute)
    || !Number.isInteger(planets) || planets < 1 || !Number.isInteger(days) || days < 1) throw new Error("Invalid replay options");
  const engine = new S2Engine(data, { seed });
  const milestones = [];
  let recorded = 0;
  for (let i = 0; i < days * 144 && engine.state.completedPlanets < planets; i += 1) {
    engine.mineBlock();
    if (engine.state.completedPlanets > recorded) {
      milestones.push({ ...engine.state.planetHistory.at(-1),
        resets: engine.state.resets, cores: engine.state.cores,
        coreLevels: { ...engine.state.coreLevels },
        totalManualLevels: engine.state.totalManualLevels,
        totalManualCommands: engine.state.totalManualCommands });
      recorded = engine.state.completedPlanets;
    }
    if (engine.state.minute % 1440 === 1200) {
      if (profile === "daily") engine.strategyVisit();
      if (coreRoute !== "none") {
        for (;;) {
          const candidates = data.prestige.upgrades.filter((spec) => engine.coreAvailable(spec.key)
            && engine.coreCost(spec.key) <= engine.state.cores
            && (coreRoute !== "speed" || spec.key === "core_drill" || spec.key === "galactic_drive"));
          candidates.sort((a, b) => engine.coreCost(a.key) - engine.coreCost(b.key));
          if (!candidates.length) break;
          engine.purchaseCore(candidates[0].key);
        }
      }
      if (engine.state.planetComplete && engine.state.resets === 0) engine.departPlanet();
    }
  }
  return { engine, milestones };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2);
  const value = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
  const data = JSON.parse(fs.readFileSync(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url)));
  const { engine, milestones } = replayPrestige(data, {
    seed: Number(value("--seed", 42)), profile: value("--profile", "daily"),
    planets: Number(value("--planets", 12)), days: Number(value("--days", 300)),
    coreRoute: value("--core-route", "balanced"),
  });
  console.log(JSON.stringify({ milestones, final: { minute: engine.state.minute,
    completedPlanets: engine.state.completedPlanets, cores: engine.state.cores,
    coreLevels: engine.state.coreLevels, speed: engine.prestigeSpeed(),
    dailyManualPeak: engine.state.maxDailyManualLevels },
  }, null, 2));
}
