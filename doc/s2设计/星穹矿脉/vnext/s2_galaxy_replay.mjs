import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { S2Engine, validateGameData } from "../../../../web/static/s2-vnext/engine.js";

export function replayGalaxy(data, { seed = 42, profile = "daily", route = "balanced", days = 600, stopAfterResearch = false } = {}) {
  if (!["daily", "absent"].includes(profile) || !["balanced", "speed", "rebuild", "burst", "off"].includes(route)
    || !Number.isInteger(days) || days <= 0) throw new Error("Invalid galaxy replay options");
  const e = new S2Engine(data, { seed });
  const stages = [];
  const research = [];
  const milestones = [];
  const marks = [1, 10, 100, 1000, 10000, 100000, 1000000, 10000000, 100000000];
  let researchComplete = null;
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
    while (marks.length && marks[0] <= e.state.completedPlanets + count) {
      const planets = marks.shift();
      milestones.push({ planets, elapsedDays: (e.state.minute + (planets - e.state.completedPlanets) * plan.duration) / 1440,
        seconds: plan.duration * 60 });
    }
    settle(plan, count);
  };
  const purchase = e.purchaseCore.bind(e);
  e.purchaseCore = (key) => {
    const item = purchase(key);
    if (item.ok) {
      research.push({ ...item, elapsedDays: e.state.minute / 1440, planets: e.state.completedPlanets });
      if (Object.values(e.coreSpecs).every((spec) => e.state.coreLevels[spec.key] === spec.maxLevel)) {
        researchComplete = { elapsedDays: e.state.minute / 1440, planets: e.state.completedPlanets };
      }
    }
    return item;
  };
  const finish = e.finishPlanet.bind(e);
  e.finishPlanet = () => {
    const ok = finish();
    if (ok) {
      const h = e.state.planetHistory.at(-1);
      collect(h.planet, h.minutes, h.completedMinute);
      while (marks.length && marks[0] <= h.planet) {
        milestones.push({ planets: marks.shift(), elapsedDays: h.completedMinute / 1440, seconds: h.minutes * 60 });
      }
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
    if (stopAfterResearch && researchComplete) break;
  }
  return { engine: e, result: { seed, profile, route, elapsedMs: performance.now() - started,
    completedPlanets: e.state.completedPlanets,
    elapsedDays: e.state.planetHistory.at(-1)?.completedMinute / 1440,
    cores: e.state.cores, coreLevels: e.state.coreLevels, compiled, events, stages, milestones, research,
    researchComplete, finalSeconds: e.state.planetHistory.at(-1)?.minutes * 60,
    productiveTailDays: researchComplete && e.galaxyComplete()
      ? e.state.planetHistory.at(-1).completedMinute / 1440 - researchComplete.elapsedDays : null } };
}

export function calibrateGalaxyGoal(data, { tailDays = 5, roundTo = 1000, ...options } = {}) {
  if (!(tailDays > 0) || !Number.isFinite(tailDays) || !Number.isSafeInteger(roundTo) || roundTo < 1) {
    throw new Error("Invalid goal calibration options");
  }
  // A roomy, safe-integer trial horizon, not the authored galaxy goal.
  const trial = structuredClone(data);
  trial.prestige.galaxyTargetPlanets = 100000000;
  const { engine, result } = replayGalaxy(trial, { ...options, stopAfterResearch: true });
  if (!result.researchComplete) throw new Error("Research did not finish within the replay horizon");
  const endgame = new S2Engine(trial, { state: engine.snapshot() });
  endgame.clearLocalPlanet();
  const seconds = endgame.voyagePlan().duration * 60;
  const exact = result.researchComplete.planets + Math.ceil(tailDays * 86400 / seconds);
  const recommendedTarget = Math.ceil(exact / roundTo) * roundTo;
  trial.prestige.galaxyTargetPlanets = recommendedTarget;
  validateGameData(trial);
  return { referenceProfile: result.profile, referenceRoute: result.route, researchComplete: result.researchComplete,
    finalSeconds: seconds, requestedTailDays: tailDays, recommendedTarget,
    actualTailDays: (recommendedTarget - result.researchComplete.planets) * seconds / 86400 };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const data = JSON.parse(fs.readFileSync(new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url)));
  const args = process.argv.slice(2);
  const value = (key, fallback) => args.includes(key) ? args[args.indexOf(key) + 1] : fallback;
  const options = { seed: Number(value("--seed", 42)), profile: value("--profile", "daily"),
    route: value("--route", "balanced"), days: Number(value("--days", 600)) };
  if (args.includes("--calibrate")) console.log(JSON.stringify(calibrateGalaxyGoal(data, options), null, 2));
  else {
    const { engine, result } = replayGalaxy(data, options);
    new S2Engine(data, { state: engine.snapshot() });
    console.log(JSON.stringify(result, null, 2));
  }
}
