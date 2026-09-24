import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { S2Engine } from "../../../../web/static/s2-vnext/engine.js";

export function replayGalaxy(data, { seed = 42, profile = "daily", route = "balanced", days = 600 } = {}) {
  if (!["daily", "absent"].includes(profile) || !["balanced", "speed", "off"].includes(route)
    || !Number.isInteger(days) || days <= 0) throw new Error("Invalid galaxy replay options");
  const e = new S2Engine(data, { seed });
  const stages = [];
  const thresholds = [86400, 3600, 60, 10, 1];
  let compiled = 0; let events = 0;
  const collect = (planet, minutes, completedMinute) => {
    while (thresholds.length && minutes * 60 <= thresholds[0]) {
      stages.push({ thresholdSeconds: thresholds.shift(), planet, seconds: minutes * 60, elapsedDays: completedMinute / 1440 });
    }
  };
  const settle = e.settleVoyages.bind(e);
  e.settleVoyages = (plan, count) => {
    collect(e.state.completedPlanets + 1, plan.duration, e.state.minute + plan.duration);
    settle(plan, count);
  };
  const finish = e.finishPlanet.bind(e);
  e.finishPlanet = () => {
    const ok = finish();
    if (ok) {
      const h = e.state.planetHistory.at(-1);
      collect(h.planet, h.minutes, h.completedMinute);
    }
    return ok;
  };
  const started = performance.now();
  for (let day = 0; day < days && !e.galaxyComplete(); day += 1) {
    e.mineBlock(1200); compiled += e.lastBatchSummary.compiled; events += e.lastBatchSummary.events;
    if (profile === "daily") e.strategyVisit();
    if (e.state.planetComplete && e.state.resets === 0) {
      e.setCoreAutoRoute(route);
      e.departPlanet();
    }
    e.mineBlock(240); compiled += e.lastBatchSummary.compiled; events += e.lastBatchSummary.events;
  }
  return { engine: e, result: { seed, profile, route, elapsedMs: performance.now() - started,
    completedPlanets: e.state.completedPlanets,
    elapsedDays: e.state.planetHistory.at(-1)?.completedMinute / 1440,
    cores: e.state.cores, coreLevels: e.state.coreLevels, compiled, events, stages } };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const data = JSON.parse(fs.readFileSync(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url)));
  const args = process.argv.slice(2);
  const value = (key, fallback) => args.includes(key) ? args[args.indexOf(key) + 1] : fallback;
  const options = { seed: Number(value("--seed", 42)), profile: value("--profile", "daily"),
    route: value("--route", "balanced"), days: Number(value("--days", 600)) };
  const { engine, result } = replayGalaxy(data, options);
  new S2Engine(data, { state: engine.snapshot() });
  console.log(JSON.stringify(result, null, 2));
}
