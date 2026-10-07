/* 角色体检报告：纳入率、输出、治疗、存活率、胜率影响 */
const path=require('path');
const M3=require(path.join(__dirname,'..','src','engine.js'));
require(path.join(__dirname,'..','src','data.js'));
let s=99; const rnd=()=>{s=(s*1664525+1013904223)>>>0;return s/4294967296;};
const LV=parseInt(process.argv[2]||'20',10);
const N=parseInt(process.argv[3]||'1200',10);
M3.tuning.enemyStatScale=0.92;
const acc={};
M3.cats.forEach(d=>acc[d.id]={name:d.title,role:d.role,in:0,win:0,dealt:0,healed:0,alive:0,rounds:0});
let totalWin=0;
for(let i=0;i<N;i++){
  const team=M3.pickBalancedTeam(M3.cats,4,rnd);
  const cats=M3.buildUnits(team.map(d=>({def:d,level:LV})),'cat');
  const n=LV<=3?3:LV<=11?4:5;
  const rats=M3.buildUnits(M3.rollEnemyTeam(LV,n,rnd),'rat');
  const r=M3.simulate(cats,rats,(rnd()*1e9)|0,false);
  if(r.win)totalWin++;
  r.stats.forEach(st=>{
    const u=cats.find(c=>c.title===st.name);
    const a=acc[u.def.id]; a.in++; if(r.win)a.win++; a.dealt+=st.dealt; a.healed+=st.healed; if(st.alive)a.alive++;
  });
}
console.log('等级 %d 采样 %d 场，整体胜率 %s%%', LV, N, (totalWin/N*100).toFixed(1));
console.log('角色            职业       纳入率   参与胜率   均输出   均治疗   存活率');
Object.values(acc).sort((a,b)=>b.in-a.in).forEach(a=>{
  if(!a.in){console.log('  %s %s  (未纳入)', pad(a.name,14), pad(a.role,8)); return;}
  console.log('  %s %s %s  %s  %s  %s  %s',
    pad(a.name,14), pad(a.role,8), pad((a.in/N*100).toFixed(1)+'%',7),
    pad((a.win/a.in*100).toFixed(1)+'%',8), pad((a.dealt/a.in).toFixed(0),7),
    pad((a.healed/a.in).toFixed(0),7), pad((a.alive/a.in*100).toFixed(1)+'%',7));
});
/* 敌方威胁榜 */
const threat={};
for(let i=0;i<N;i++){
  const cats=M3.buildUnits(M3.pickBalancedTeam(M3.cats,4,rnd).map(d=>({def:d,level:LV})),'cat');
  const n=LV<=3?3:LV<=11?4:5;
  const rats=M3.buildUnits(M3.rollEnemyTeam(LV,n,rnd),'rat');
  const r=M3.simulate(cats,rats,(rnd()*1e9)|0,false);
  r.stats.forEach(st=>{ /* 只用敌方输出做威胁：从事件流统计太重，这里用回合数近似 */
  });
}
function pad(s,w){s=String(s);return s+' '.repeat(Math.max(0,w-s.length));}
