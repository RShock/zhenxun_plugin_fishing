import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.resolve(here, "../../../../web/static/s2-vnext");
const { runReplay, validateGameData } = await import(pathToFileURL(path.join(webDir, "engine.js")).href);
const data = validateGameData(JSON.parse(fs.readFileSync(path.join(webDir, "game_data.json"), "utf8")));
const [seed = "42", days = "10", profile = "active", route = "balanced"] = process.argv.slice(2);
const result = runReplay(data, { seed: Number(seed), days: Number(days), profile, route });
process.stdout.write(JSON.stringify({
  snapshots: result.snapshots,
  events: result.events,
  levels: result.engine.state.levels,
  manualLevels: result.engine.state.manualLevels,
  autoUnlocked: [...result.engine.state.autoUnlocked].sort(),
  helperEnabled: result.engine.state.helperEnabled,
  nextHelperMinute: result.engine.state.nextHelperMinute,
  totalHelperLevels: result.engine.state.totalHelperLevels,
  totalManualLevels: result.engine.state.totalManualLevels,
  totalManualCommands: result.engine.state.totalManualCommands,
  totalAutoLevels: result.engine.state.totalAutoLevels,
  lastHelperReport: result.engine.state.lastHelperReport,
}));
