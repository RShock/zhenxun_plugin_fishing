/* ==========================================================================
 * map3 · 平衡模拟器（Node CLI）
 * --------------------------------------------------------------------------
 * 用法：
 *   node tools/sim.js                 # 默认：等战力编队 vs 随机杂兵，按等级扫一遍
 *   node tools/sim.js --n=2000        # 提高迭代次数
 *   node tools/sim.js --levels=1,5,10,15,20
 *   node tools/sim.js --random        # 完全随机编队（不保证势均力敌）
 *   node tools/sim.js --enemies=4     # 指定敌人数量
 *   node tools/sim.js --verbose       # 打印一场战斗的战报
 * ========================================================================== */
const path = require('path');
const M3 = require(path.join(__dirname, '..', 'src', 'engine.js'));
require(path.join(__dirname, '..', 'src', 'data.js'));

const argv = process.argv.slice(2);
function opt(name, def) {
  const hit = argv.find(a => a.startsWith('--' + name + '='));
  return hit ? hit.split('=')[1] : def;
}
const has = n => argv.includes('--' + n);

const N = parseInt(opt('n', '800'), 10);
const LEVELS = opt('levels', '1,5,10,15,20').split(',').map(Number);
const FIXED_ENEMIES = opt('enemies', null) ? parseInt(opt('enemies'), 10) : null;
const RANDOM_TEAMS = has('random');
const ENEMY_SCALE = opt('enemyScale', null);
if (ENEMY_SCALE !== null && M3.tuning) M3.tuning.enemyStatScale = parseFloat(ENEMY_SCALE);

/* 可复现的伪随机 */
let seedState = 20261007;
function rnd() {
  seedState = (seedState * 1664525 + 1013904223) >>> 0;
  return seedState / 4294967296;
}

function buildEnemies(level, n) {
  const specs = M3.rollEnemyTeam(level, n, rnd);
  return M3.buildUnits(specs, 'rat');
}

const agg = {};
for (const lv of LEVELS) {
  const n = FIXED_ENEMIES || (lv <= 3 ? 3 : lv <= 11 ? 4 : 5);
  const row = { lv, n, win: 0, rounds: 0, survivors: 0, hp: 0, teams: 0, turns: 0, allTurns: 0,
                catDealt: {}, catTurns: {}, ultTurns: {}, test: 0, mouseDealt: {}, mouseTurns: {}, mouseUlt: {} };
  for (let i = 0; i < N; i++) {
    const team = RANDOM_TEAMS ? shuffle(M3.cats.slice()).slice(0, 4) : M3.pickBalancedTeam(M3.cats, 4, rnd);
    const cats = M3.buildUnits(team.map(d => ({ def: d, level: lv })), 'cat');
    const rats = buildEnemies(lv, n);
    const res = M3.simulate(cats, rats, (rnd() * 1e9) | 0, i < 60 || has('verbose'));
    if (res.win) row.win++;
    row.rounds += res.ticks;
    row.turns += res.turns;
    row.survivors += res.catsAlive;
    row.hp += res.catHpPct;
    row.teams += team.length;
    res.stats.forEach(s => {
      row.catDealt[s.name] = (row.catDealt[s.name] || 0) + s.dealt;
      row.catTurns[s.name] = (row.catTurns[s.name] || 0) + 1;
    });
    /* 技能使用率统计（按事件流） */
    for (const e of res.events) {
      if (e.t === 'turn') row.allTurns++;
      if (e.t === 'skill' && e.skill !== 'basic') {
        const key = e.uid.split(':')[1];
        row.ultTurns[key] = (row.ultTurns[key] || 0) + 1;
        row.test++;
      }
      if (e.t === 'turn' && e.uid.startsWith('rat:')) {
        row.mouseTurns[e.uid.split(':')[1]] = (row.mouseTurns[e.uid.split(':')[1]] || 0) + 1;
      }
    }
  }
  row.ticksPerRound = row.rounds / N;
  row.actionsPer = row.turns / N;
  agg[lv] = row;
}

function shuffle(a) { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

/* -------------------------------- 输出 -------------------------------- */
console.log('=== map3 平衡模拟 ===  迭代/档: %d   编队: %s   敌人数量: 3/4/5(按等级) ===',
  N, RANDOM_TEAMS ? '随机' : '等战力4人');
console.log('等级  敌人  胜率     平均刻度  平均行动  存活猫  剩余血量%  大招占比');
for (const lv of LEVELS) {
  const r = agg[lv];
  console.log('%s   %s    %s   %s    %s    %s    %s     %s',
    pad(lv, 4), pad(r.n, 4),
    pad((r.win / N * 100).toFixed(1) + '%', 8),
    pad(r.ticksPerRound.toFixed(1), 8),
    pad(r.actionsPer.toFixed(1), 8),
    pad((r.survivors / N).toFixed(2), 6),
    pad((r.hp / N * 100).toFixed(1), 8),
    r.allTurns ? (100 * r.test / r.allTurns).toFixed(0) + '%' : '-');
}

/* 角色输出榜（最高等级档） */
const last = agg[LEVELS[LEVELS.length - 1]];
console.log('\n--- 我方角色输出榜（等级 %d，累计伤害/场次） ---', last.lv);
Object.entries(last.catDealt)
  .map(([k, v]) => [k, v / last.catTurns[k]])
  .sort((a, b) => b[1] - a[1])
  .forEach(([k, v]) => console.log('  %s  %s', pad(k, 16), v.toFixed(0)));

console.log('\n--- 敌方杂兵行动占比（等级 %d） ---', last.lv);
const tot = Object.values(last.mouseTurns).reduce((a, b) => a + b, 0) || 1;
Object.entries(last.mouseTurns).sort((a, b) => b[1] - a[1]).slice(0, 12)
  .forEach(([k, v]) => console.log('  %s  %s%%', pad(k, 16), (v / tot * 100).toFixed(1)));

/* 单场战报 */
if (has('verbose')) {
  console.log('\n--- 样例战报 ---');
  showOne(LEVELS[LEVELS.length - 1]);
}

function showOne(lv) {
  const team = M3.pickBalancedTeam(M3.cats, 4, rnd);
  const cats = M3.buildUnits(team.map(d => ({ def: d, level: lv })), 'cat');
  const rats = buildEnemies(lv, 4);
  const res = M3.simulate(cats, rats, 12345, true);
  const inst = {};
  cats.concat(rats).forEach(u => { inst[u.uid] = u; });
  const lines = [];
  let round = 1, acts = 0;
  for (const e of res.events) {
    if (e.t === 'turn') { acts++; if (acts % 4 === 1) lines.push(`  ── 第 ${round++} 轮 ──`); }
    else if (e.t === 'skill') lines.push(`  ${inst[e.uid].title} 使用【${e.name}】`);
    else if (e.t === 'damage') lines.push(`     → ${inst[e.tid].title} -${e.value}${e.crit ? ' 暴击!' : ''}`);
    else if (e.t === 'heal') lines.push(`     + ${inst[e.tid].title} +${e.value} (${e.label || '治疗'})`);
    else if (e.t === 'death') lines.push(`  ✝ ${inst[e.uid].title} 倒下了`);
  }
  console.log(lines.slice(0, 120).join('\n'));
  console.log('  结果：%s（剩余 %d 猫 / %d 鼠，%d 刻度）', res.win ? '我方胜利' : '我方失败', res.catsAlive, res.ratsAlive, res.ticks);
}

function pad(s, w) { s = String(s); return s + ' '.repeat(Math.max(0, w - s.length)); }
