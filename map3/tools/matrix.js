/* 生成平衡矩阵：我方等级 × 敌方等级 → 胜率，供设计文档与网页“预计胜率”使用 */
const fs = require('fs');
const path = require('path');
const M3 = require(path.join(__dirname, '..', 'src', 'engine.js'));
require(path.join(__dirname, '..', 'src', 'data.js'));

let s = 424242;
const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
const N = parseInt(process.argv[2] || '140', 10);
const out = { samples: N, scale: M3.tuning.enemyStatScale, cells: {} };

for (let cl = 1; cl <= 20; cl++) {
  for (let rl = 1; rl <= 20; rl++) {
    const n = rl <= 3 ? 3 : rl <= 11 ? 4 : 5;
    let win = 0, hp = 0, alive = 0, ticks = 0;
    for (let i = 0; i < N; i++) {
      const team = M3.pickBalancedTeam(M3.cats, 4, rnd, { level: cl });
      const cats = M3.buildUnits(team.map(d => ({ def: d, level: cl })), 'cat');
      const rats = M3.buildUnits(M3.rollEnemyTeam(rl, n, rnd), 'rat');
      const r = M3.simulate(cats, rats, (rnd() * 1e9) | 0, false);
      if (r.win) win++;
      hp += r.catHpPct; alive += r.catsAlive; ticks += r.ticks;
    }
    out.cells[cl + '-' + rl] = {
      win: +(win / N).toFixed(4),
      hp: +(hp / N).toFixed(3),
      alive: +(alive / N).toFixed(2),
      ticks: Math.round(ticks / N)
    };
  }
  process.stdout.write('cat level ' + cl + ' done\n');
}
fs.writeFileSync(path.join(__dirname, '..', 'src', 'balance-matrix.json'), JSON.stringify(out));
console.log('written map3/src/balance-matrix.json', JSON.stringify({ samples: N, scale: out.scale }));
