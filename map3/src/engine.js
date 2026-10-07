/* ==========================================================================
 * map3 · 猫鼠远洋 —— 自动战斗引擎（整数数值版）
 * --------------------------------------------------------------------------
 * · 行动条（速度累积）决定出手顺序，速度直接换算出手频率
 * · 乘法伤害：DMG = ATK × 倍率% × 50/(50+防御×(1-穿甲%)) × 增伤 × 暴击 × 浮动
 * · 所有技能数值以「整数百分点」存储，运行时按等级解析：值(L) = 基础 + 每级增量×(L-1)
 * · 全自动：每名单位按技能 ai 优先级与条件自行决策
 * ========================================================================== */
(function (root) {
  var M3 = (root.M3 = root.M3 || {});

  /* -------------------------------- 工具 -------------------------------- */
  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  M3.rng = mulberry32;

  var STATUS_LABEL = {
    atkUp: '攻击↑', atkDown: '攻击↓', defUp: '防御↑', defDown: '防御↓',
    spdUp: '速度↑', spdDown: '速度↓', critUp: '暴击↑', dodge: '闪避↑',
    vuln: '易伤', shield: '护盾', stun: '晕眩', taunt: '嘲讽',
    burn: '灼烧', poison: '中毒', regen: '回春', counter: '反击'
  };
  var NEGATIVE = { atkDown: 1, defDown: 1, spdDown: 1, vuln: 1, stun: 1, burn: 1, poison: 1 };
  M3.STATUS_LABEL = STATUS_LABEL;

  var DEF_K = 50;
  var CRIT_DMG_BASE = 150;   /* 整数百分点：150 = 1.5 倍 */
  var EN_MAX = 100, EN_BASIC = 20, EN_HIT = 8;
  var MAX_TICKS = 700;
  M3.tuning = { enemyStatScale: 1.0 };  /* 要塞难度旋钮；杂兵强度已写入基础值 */

  /* ---------------------------- 数值解析（整数 → 系数） ---------------------------- */
  /* spec 支持：数字 | {b,i,cap} | '%键名'（指向技能 vals，技能对象通过参数传入） | '-%键名' */
  function specRaw(spec, u, skill) {
    var neg = false, s = spec;
    if (typeof s === 'string') {
      if (s.charAt(0) === '-') { neg = true; s = s.slice(1); }
      if (s.charAt(0) === '%') {
        var key = s.slice(1);
        var v = skill && skill.vals ? skill.vals[key] : undefined;
        var out = M3.resolve(v, u ? u.level : 1);
        return neg ? -out : out;
      }
      var num = Number(s);
      return neg ? -num : num;
    }
    var r = M3.resolve(s, u ? u.level : 1);
    return neg ? -r : r;
  }
  var N = specRaw;                                   /* 计数 / 原始整数 */
  function F(spec, u, skill) { return specRaw(spec, u, skill) / 100; }  /* 百分点 → 系数 */
  M3.N = N; M3.F = F;

  /* ---------------------------- 单位实例化 ---------------------------- */
  function collectMod(def, lv) {
    var mod = {
      atkPct: 0, defPct: 0, spdPct: 0, hpPct: 0, critAdd: 0, critDmgAdd: 0,
      dmgTaken: 0, defPen: 0, dodge: 0, lifesteal: 0, healUp: 0, dotTaken: 0, rampAtk: null
    };
    var fake = { level: lv };
    (def.passives || []).forEach(function (p) {
      if (!p.stat) return;
      Object.keys(p.stat).forEach(function (k) {
        var raw = F(p.stat[k], fake, p);          /* 百分点 → 系数 */
        if (k === 'rampAtk') {
          var arr = p.stat.rampAtk;
          mod.rampAtk = [F(arr[0], fake, p), F(arr[1], fake, p)];
        } else if (k === 'critAdd' || k === 'critDmgAdd') {
          mod[k] += F(p.stat[k], fake, p);        /* 暴击点数是百分点 */
        } else if (k in mod) {
          mod[k] += raw;
        }
      });
    });
    return mod;
  }

  M3.makeUnit = function (def, level, side) {
    var s = M3.statAt(def.base, level);
    if (side === 'rat') {
      var k = (M3.tuning && M3.tuning.enemyStatScale) || 1;
      if (k !== 1) {
        s.hp = Math.round(s.hp * k);
        s.atk = Math.round(s.atk * k);
        s.def = Math.round(s.def * k);
      }
    }
    var mod = collectMod(def, level);
    var maxHp = Math.round(s.hp * (1 + mod.hpPct));
    return {
      uid: side + ':' + def.id, def: def, side: side,
      name: def.name, title: def.title || def.name, role: def.role, color: def.color,
      level: level, base: s, mod: mod,
      maxHp: maxHp, hp: maxHp,
      critDmg: CRIT_DMG_BASE / 100 + mod.critDmgAdd,
      en: 0, enMax: EN_MAX, gauge: 0, haste: 0, dead: false,
      statuses: [], usedOnce: {},
      stats: { dealt: 0, taken: 0, healed: 0, kills: 0, crits: 0 }
    };
  };

  /* ---------------------------- 动态属性计算 ---------------------------- */
  function statusSum(u, id) {
    var v = 0;
    for (var i = 0; i < u.statuses.length; i++) if (u.statuses[i].id === id) v += (u.statuses[i].value || 0);
    return v;
  }
  function hasStatus(u, id) {
    for (var i = 0; i < u.statuses.length; i++) if (u.statuses[i].id === id) return true;
    return false;
  }
  function effAtk(u) {
    var v = u.base.atk * (1 + u.mod.atkPct + statusSum(u, 'atkUp') - statusSum(u, 'atkDown'));
    if (u.mod.rampAtk) {
      var lost = 1 - u.hp / u.maxHp;
      v *= 1 + Math.min(u.mod.rampAtk[1], lost * u.mod.rampAtk[0] * 10);  /* 每损失 10% 生效一次 */
    }
    return Math.max(1, v);
  }
  function effDef(u) {
    return Math.max(0, u.base.def * (1 + u.mod.defPct + statusSum(u, 'defUp') - statusSum(u, 'defDown')));
  }
  function effSpd(u) {
    return Math.max(1, u.base.spd * (1 + u.mod.spdPct + statusSum(u, 'spdUp') - statusSum(u, 'spdDown')));
  }
  function effCrit(u) {
    return Math.max(0, Math.min(0.95, u.base.crit / 100 + u.mod.critAdd + statusSum(u, 'critUp')));
  }
  function effDodge(u) {
    return Math.max(0, Math.min(0.6, u.mod.dodge + statusSum(u, 'dodge')));
  }
  M3.eff = { atk: effAtk, def: effDef, spd: effSpd, crit: effCrit, dodge: effDodge };

  /* ------------------------------ 战场上下文 ------------------------------ */
  function makeCtx(playerUnits, enemyUnits, seed, logging) {
    return {
      rnd: mulberry32(seed || 1), log: logging !== false,
      units: playerUnits.concat(enemyUnits), ev: [], tickCount: 0, turnNo: 0,
      get cats() { return playerUnits; },
      get rats() { return enemyUnits; }
    };
  }
  function alive(list) {
    var out = [];
    for (var i = 0; i < list.length; i++) if (!list[i].dead) out.push(list[i]);
    return out;
  }
  function enemiesOf(ctx, u) { return u.side === 'cat' ? ctx.rats : ctx.cats; }
  function alliesOf(ctx, u) { return u.side === 'cat' ? ctx.cats : ctx.rats; }
  function push(ctx, e) { if (ctx.log) ctx.ev.push(e); }
  function hpPct(u) { return u.hp / u.maxHp; }

  /* -------------------------------- 条件 -------------------------------- */
  function checkCond(cond, u, ctx, tgt, skill) {
    if (!cond) return true;
    var v = F(cond.v, u, skill);
    switch (cond.c) {
      case 'always': return true;
      case 'selfHpBelow': return hpPct(u) < v;
      case 'selfHpAbove': return hpPct(u) > v;
      case 'allyHpBelow': return alive(alliesOf(ctx, u)).some(function (a) { return hpPct(a) < v; });
      case 'targetHpBelow': {
        var t = tgt || ctx.lastTarget;
        return !!t && !t.dead && hpPct(t) < v;
      }
      case 'enemyCountGE': return alive(enemiesOf(ctx, u)).length >= v;
      case 'enemiesWithDot':
        return alive(enemiesOf(ctx, u)).some(function (e) {
          return e.statuses.some(function (s) { return s.dot; });
        });
      case 'turnLE': return ctx.turnNo <= v;
      default: return true;
    }
  }

  /* ------------------------------ 目标选择 ------------------------------ */
  function lowestHp(list) {
    var best = null;
    for (var i = 0; i < list.length; i++) {
      if (list[i].dead) continue;
      if (!best || hpPct(list[i]) < hpPct(best)) best = list[i];
    }
    return best;
  }
  function highestAtk(list) {
    var best = null;
    for (var i = 0; i < list.length; i++) {
      if (list[i].dead) continue;
      if (!best || effAtk(list[i]) > effAtk(best)) best = list[i];
    }
    return best;
  }
  function lowestEnergy(list) {
    var best = null;
    for (var i = 0; i < list.length; i++) {
      if (list[i].dead) continue;
      if (!best || list[i].en < best.en) best = list[i];
    }
    return best;
  }
  function pickTargets(sel, u, ctx) {
    var foes = alive(enemiesOf(ctx, u));
    var mates = alive(alliesOf(ctx, u));
    var taunts = (sel === 'one' || sel === 'oneHighestAtk')
      ? foes.filter(function (e) { return hasStatus(e, 'taunt'); }) : [];
    switch (sel) {
      case 'all': return foes;
      case 'random': return foes.length ? [foes[Math.floor(ctx.rnd() * foes.length)]] : [];
      case 'oneHighestAtk': return taunts.length ? [lowestHp(taunts)] : (highestAtk(foes) ? [highestAtk(foes)] : []);
      case 'self': return [u];
      case 'allAllies': return mates;
      case 'lowestAlly': return lowestHp(mates) ? [lowestHp(mates)] : [];
      case 'lowestEnergyAlly': return lowestEnergy(mates) ? [lowestEnergy(mates)] : [];
      case 'attacker': return ctx.attacker && !ctx.attacker.dead ? [ctx.attacker] : [];
      case 'lastHit': return ctx.lastTarget && !ctx.lastTarget.dead ? [ctx.lastTarget] : (foes.length ? [foes[0]] : []);
      case 'randomEnemy': return foes.length ? [foes[Math.floor(ctx.rnd() * foes.length)]] : [];
      case 'one':
      default: return taunts.length ? [lowestHp(taunts)] : (lowestHp(foes) ? [lowestHp(foes)] : []);
    }
  }

  /* -------------------------------- 伤害 -------------------------------- */
  function damageModFromTriggers(src, tgt, ctx) {
    var mult = 1;
    (src.def.passives || []).forEach(function (p) {
      (p.triggers || []).forEach(function (tr) {
        if (tr.on !== 'onBeforeDamage') return;
        if (!checkCond(tr.cond, src, ctx, tgt, p)) return;
        if (tr.effect.kind === 'damageMod') mult *= 1 + F(tr.effect.value, src, p);
      });
    });
    return mult;
  }

  function dealDamage(src, tgt, step, ctx, opts) {
    opts = opts || {};
    var ev = { t: 'damage', src: src.uid, tid: tgt.uid, crit: false, dodged: false };
    if (!src || !tgt || tgt.dead || src.dead) return 0;

    if (!opts.trueDamage && !opts.noDodge && effDodge(tgt) > 0 && ctx.rnd() < effDodge(tgt)) {
      ev.dodged = true; push(ctx, ev);
      push(ctx, { t: 'miss', tid: tgt.uid });
      return 0;
    }

    var atk = effAtk(src);
    var def = effDef(tgt) * (1 - Math.max(0, Math.min(0.8, src.mod.defPen)));
    var mit = DEF_K / (DEF_K + def);
    var dmg = atk * F(step.mul, src, opts.skill) * mit;

    dmg *= damageModFromTriggers(src, tgt, ctx);
    if (step.execute) {
      var below = F(step.execute.below, src, opts.skill);
      var bonus = F(step.execute.bonus, src, opts.skill);
      if (hpPct(tgt) < below) dmg *= 1 + bonus;
    }
    if (step.bonusVsStunned && hasStatus(tgt, 'stun')) dmg *= 1 + F(step.bonusVsStunned, src, opts.skill);
    dmg *= 1 + statusSum(tgt, 'vuln');
    dmg *= 1 + tgt.mod.dmgTaken;

    var crit = ctx.rnd() < effCrit(src);
    if (crit) { dmg *= src.critDmg; src.stats.crits++; }
    if (crit && !src.dead) runTriggers(src, 'onCrit', ctx);   /* 暴击触发（元素充能等） */
    dmg *= 0.94 + ctx.rnd() * 0.12;

    dmg = Math.max(1, Math.round(dmg));
    ev.crit = opts.trueDamage ? false : crit;

    var absorbed = 0;
    for (var i = 0; i < tgt.statuses.length && dmg > 0; i++) {
      var s = tgt.statuses[i];
      if (s.id !== 'shield' || !s.absorb) continue;
      var take = Math.min(s.absorb, dmg);
      s.absorb -= take; dmg -= take; absorbed += take;
      if (s.absorb <= 0) tgt.statuses.splice(i--, 1);
    }
    if (absorbed) push(ctx, { t: 'absorb', tid: tgt.uid, value: absorbed });

    tgt.hp -= dmg;
    src.stats.dealt += dmg;
    tgt.stats.taken += dmg;
    ev.value = dmg; ev.targetHp = Math.max(0, tgt.hp);
    push(ctx, ev);

    ctx.lastTarget = tgt;
    ctx.attacker = src;

    var ls = src.mod.lifesteal + (step.lifesteal ? F(step.lifesteal, src, opts.skill) : 0);
    if (ls > 0 && dmg > 0) healUnit(src, src, Math.round(dmg * ls), ctx, '吸血');

    if (!opts.trueDamage && !opts.noCounter && alive(enemiesOf(ctx, tgt)).indexOf(src) >= 0) {
      var cval = statusSum(tgt, 'counter');
      if (cval > 0 && !src.dead && !tgt.dead) {
        push(ctx, { t: 'counter', uid: tgt.uid });
        dealDamage(tgt, src, { mul: cval * 100 }, ctx, { noCounter: true, skill: opts.skill });
      }
    }

    if (!src.dead && !tgt.dead) runTriggers(tgt, 'onTakeDamage', ctx, { attacker: src, lastTarget: tgt });
    return dmg;
  }

  function damageAfterDeath(ctx) {
    ctx.units.forEach(function (u) {
      if (!u.dead && u.hp <= 0) {
        u.hp = 0; u.dead = true; u.statuses = [];
        push(ctx, { t: 'death', uid: u.uid });
        var a = ctx.attacker;
        if (a && a.side !== u.side) a.stats.kills++;
      }
    });
  }

  function healBonus(src, tgt, ctx) {
    var bonus = src.mod.healUp;
    alliesOf(ctx, tgt).forEach(function (a) { if (a !== src && !a.dead) bonus += a.mod.healUp; });
    return 1 + bonus;
  }

  function healUnit(src, tgt, amount, ctx, label) {
    if (tgt.dead) return 0;
    var heal = Math.round(amount * healBonus(src, tgt, ctx));
    var before = tgt.hp;
    tgt.hp = Math.min(tgt.maxHp, tgt.hp + heal);
    var real = tgt.hp - before;
    src.stats.healed += real;
    push(ctx, { t: 'heal', tid: tgt.uid, value: real, label: label || '治疗' });
    return real;
  }

  /* ------------------------------- 状态施加 ------------------------------- */
  function applyStatus(u, spec, ctx, srcUnit) {
    if (u.dead) return;
    var st = { id: spec.status, value: spec.value || 0, turns: spec.turns || 2, src: srcUnit ? srcUnit.uid : null };
    if (spec.status === 'shield') st.absorb = spec.absorb || 0;
    if (spec.dot) st.dot = spec.dot;
    if (spec.stackMax) {
      var same = u.statuses.filter(function (s) { return s.id === spec.status && s.src === st.src; }).length;
      if (same >= spec.stackMax) return;
    }
    u.statuses.push(st);
    push(ctx, {
      t: 'status', tid: u.uid, status: st.id, label: STATUS_LABEL[st.id] || st.id,
      value: st.value, turns: st.turns, absorb: st.absorb || 0
    });
  }

  /* ------------------------------- 步骤执行 ------------------------------- */
  function executeStep(step, u, ctx, skill) {
    var sk = skill || step;
    switch (step.kind) {
      case 'damage': {
        var hits = N(step.hits, u, sk) || 1;
        var total = 0;
        for (var h = 0; h < hits; h++) {
          var tgts = pickTargets(step.target || 'one', u, ctx);
          if (!tgts.length) break;
          for (var i = 0; i < tgts.length; i++) {
            if (tgts[i].dead) continue;
            total += dealDamage(u, tgts[i], step, ctx, { skill: sk });
          }
        }
        return total;
      }
      case 'heal': {
        var hs = pickTargets(step.target || 'self', u, ctx);
        for (var j = 0; j < hs.length; j++) healUnit(u, hs[j], effAtk(u) * F(step.mul, u, sk), ctx);
        return hs.length;
      }
      case 'shield': {
        var ss = pickTargets(step.target || 'self', u, ctx);
        for (var k = 0; k < ss.length; k++) {
          applyStatus(ss[k], {
            status: 'shield', absorb: Math.round(effAtk(u) * F(step.mul, u, sk)),
            turns: N(step.turns, u, sk) || 2
          }, ctx, u);
        }
        return ss.length;
      }
      case 'status': {
        var ts = pickTargets(step.target || 'one', u, ctx);
        for (var m = 0; m < ts.length; m++) {
          if (step.chance !== undefined && ctx.rnd() > F(step.chance, u, sk)) {
            push(ctx, { t: 'resist', tid: ts[m].uid, label: STATUS_LABEL[step.status] || step.status });
            continue;
          }
          applyStatus(ts[m], {
            status: step.status, value: F(step.value, u, sk),
            turns: N(step.turns, u, sk), stackMax: step.stackMax
          }, ctx, u);
        }
        return ts.length;
      }
      case 'dot': {
        var ds = pickTargets(step.target || 'one', u, ctx);
        for (var n = 0; n < ds.length; n++) {
          applyStatus(ds[n], {
            status: step.id, value: Math.round(effAtk(u) * F(step.mul, u, sk)),
            turns: N(step.turns, u, sk) || 2, dot: step.id
          }, ctx, u);
        }
        return ds.length;
      }
      case 'detonate': {
        var xs = pickTargets(step.target || 'one', u, ctx);
        var count = 0;
        xs.forEach(function (x) {
          var stacks = x.statuses.filter(function (s) { return s.dot === step.dotId; }).slice(0, step.maxStacks || 3);
          stacks.forEach(function () {
            var dmg = Math.max(1, Math.round(effAtk(u) * F(step.mul, u, sk)));
            push(ctx, { t: 'detonate', tid: x.uid, value: dmg });
            x.hp -= dmg; u.stats.dealt += dmg; x.stats.taken += dmg;
            if (x.hp <= 0) damageAfterDeath(ctx);
            count++;
          });
          x.statuses = x.statuses.filter(function (s) { return s.dot !== step.dotId; });
        });
        return count;
      }
      case 'cleanse': {
        var cs = pickTargets(step.target || 'self', u, ctx);
        var removed = 0;
        cs.forEach(function (c) {
          for (var i2 = 0; i2 < c.statuses.length && removed < (N(step.count, u, sk) || 1); i2++) {
            if (NEGATIVE[c.statuses[i2].id]) { c.statuses.splice(i2, 1); i2--; removed++; }
          }
        });
        push(ctx, { t: 'cleanse', tid: cs.length ? cs[0].uid : null, value: removed });
        return removed;
      }
      case 'energy': {
        var es = pickTargets(step.target || 'self', u, ctx);
        var amt = N(step.amount, u, sk);
        es.forEach(function (e) { e.en = Math.min(e.enMax, e.en + amt); });
        push(ctx, { t: 'energy', tid: es.length ? es[0].uid : null, value: amt });
        return es.length;
      }
      case 'haste': {
        var target = pickTargets(step.target || 'self', u, ctx)[0] || u;
        target.haste += 1;
        push(ctx, { t: 'haste', tid: target.uid });
        return 1;
      }
      case 'selfHpCost': {
        var cost = Math.round(u.maxHp * F(step.v, u, sk));
        u.hp = Math.max(1, u.hp - cost);
        u.stats.taken += cost;
        push(ctx, { t: 'selfcost', uid: u.uid, value: cost });
        return cost;
      }
      case 'damageMod':
        return 0;
      default: return 0;
    }
  }

  function runTriggers(u, hook, ctx, extra) {
    if (u.dead) return;
    var old = {};
    if (extra) Object.keys(extra).forEach(function (k) { old[k] = ctx[k]; ctx[k] = extra[k]; });
    (u.def.passives || []).forEach(function (p) {
      /* 等级不足未解锁的被动不生效 */
      if ((p.unlock || 1) > u.level) return;
      (p.triggers || []).forEach(function (tr, idx) {
        if (tr.on !== hook) return;
        var key = p.id + ':' + hook + ':' + idx;
        if (tr.once && u.usedOnce[key]) return;
        if (tr.chanceVal !== undefined && ctx.rnd() > F(tr.chanceVal, u, p)) return;
        if (!checkCond(tr.cond, u, ctx, extra && extra.lastTarget, p)) return;
        if (tr.once) u.usedOnce[key] = 1;
        executeStep(tr.effect, u, ctx, p);
      });
    });
    if (extra) Object.keys(extra).forEach(function (k) { ctx[k] = old[k]; });
  }

  /* ------------------------------- 技能决策 ------------------------------- */
  function chooseSkill(u, ctx) {
    var best = null;
    function consider(skill, prio) { if (!best || prio > best.prio + 1e-9) best = { skill: skill, prio: prio }; }
    consider(null, 0);
    (u.def.ults || []).forEach(function (ult) {
      if ((ult.unlock || 1) > u.level) return;      /* 未解锁 */
      if (u.en < ult.cost) return;
      var prio = (ult.ai && ult.ai.prio) || 0;
      if (ult.ai && ult.ai.cond && !checkCond(ult.ai.cond, u, ctx, null, ult)) prio = Math.min(prio, 0.5);
      consider(ult, prio);
    });
    return best.skill;
  }

  /* -------------------------------- 行动 -------------------------------- */
  function tickStatuses(u, ctx) {
    for (var i = 0; i < u.statuses.length; i++) {
      var s = u.statuses[i];
      if (s.dot === 'burn' || s.dot === 'poison') {
        var dmg = Math.max(1, Math.round(s.value * (1 + u.mod.dotTaken)));
        u.hp -= dmg; u.stats.taken += dmg;
        push(ctx, { t: 'dot', tid: u.uid, status: s.dot, label: STATUS_LABEL[s.dot], value: dmg });
        if (s.src) {
          var src = ctx.units.filter(function (x) { return x.uid === s.src; })[0];
          if (src) src.stats.dealt += dmg;
        }
      } else if (s.id === 'regen') {
        var before = u.hp;
        u.hp = Math.min(u.maxHp, u.hp + s.value);
        if (u.hp > before) push(ctx, { t: 'heal', tid: u.uid, value: u.hp - before, label: '回春' });
      }
    }
    damageAfterDeath(ctx);
  }

  function expireStatuses(u) {
    for (var i = u.statuses.length - 1; i >= 0; i--) {
      var s = u.statuses[i];
      if (s.turns === 99) continue;
      s.turns--;
      if (s.turns <= 0) u.statuses.splice(i, 1);
    }
  }

  function runBasicAttack(u, ctx) {
    var special = null, spSkill = null;
    (u.def.passives || []).forEach(function (p) {
      if (p.triggerSpecial && (p.unlock || 1) <= u.level) { special = p.triggerSpecial; spSkill = p; }
    });
    if (special && special.kind === 'spread' && ctx.rnd() < F(special.chanceVal, u, spSkill)) {
      push(ctx, { t: 'special', uid: u.uid, label: '散弹装填' });
      executeStep({ kind: 'damage', mul: special.mulVal, target: 'all' }, u, ctx, null);
      return;
    }
    executeStep({ kind: 'damage', mul: 100, target: 'one' }, u, ctx, null);
    if (special && special.kind === 'pursuit' && ctx.rnd() < F(special.chanceVal, u, spSkill)) {
      push(ctx, { t: 'special', uid: u.uid, label: '追击' });
      executeStep({ kind: 'damage', mul: special.mulVal, target: 'one' }, u, ctx, null);
    }
  }

  function act(u, ctx) {
    ctx.turnNo++;
    push(ctx, { t: 'turn', uid: u.uid });

    tickStatuses(u, ctx);
    if (u.dead) return;

    runTriggers(u, 'onTurnStart', ctx);
    damageAfterDeath(ctx);
    if (u.dead) return;

    if (hasStatus(u, 'stun')) {
      push(ctx, { t: 'skip', uid: u.uid, label: '晕眩' });
    } else {
      var skill = chooseSkill(u, ctx);
      if (skill) {
        u.en -= skill.cost;
        push(ctx, { t: 'skill', uid: u.uid, skill: skill.id, name: skill.name, cost: skill.cost });
        skill.steps.forEach(function (s) { if (!u.dead) executeStep(s, u, ctx, skill); });
      } else {
        push(ctx, { t: 'skill', uid: u.uid, skill: 'basic', name: '普通攻击', cost: 0 });
        runBasicAttack(u, ctx);
        u.en = Math.min(u.enMax, u.en + EN_BASIC);
      }
      runTriggers(u, 'onAttack', ctx);
    }
    damageAfterDeath(ctx);
    if (u.dead) return;

    runTriggers(u, 'onTurnEnd', ctx);
    damageAfterDeath(ctx);
    expireStatuses(u);
  }

  /* 暴击回能等：由 dealDamage 内部触发 */
  function hookCrit(u, ctx) { runTriggers(u, 'onCrit', ctx); }

  /* -------------------------------- 主循环 -------------------------------- */
  M3.simulate = function (cats, rats, seed, logging) {
    var ctx = makeCtx(cats, rats, seed, logging);
    push(ctx, { t: 'start' });
    var guard = 0;
    while (guard++ < MAX_TICKS * 4) {
      if (!alive(ctx.cats).length || !alive(ctx.rats).length) break;
      var ready = [];
      ctx.units.forEach(function (u) { if (!u.dead && u.gauge >= 100) ready.push(u); });
      if (ready.length) {
        ready.sort(function (a, b) {
          if (b.gauge !== a.gauge) return b.gauge - a.gauge;
          return effSpd(b) - effSpd(a);
        });
        var u2 = ready[0];
        u2.gauge -= 100;
        act(u2, ctx);
        if (u2.haste > 0) { u2.haste--; u2.gauge = 100; }
        continue;
      }
      ctx.units.forEach(function (u) { if (!u.dead) u.gauge += effSpd(u); });
      ctx.tickCount++;
      if (ctx.tickCount > MAX_TICKS) break;
    }

    var catsAlive = alive(ctx.cats).length, ratsAlive = alive(ctx.rats).length;
    var win;
    if (ratsAlive === 0 && catsAlive > 0) win = true;
    else if (catsAlive === 0) win = false;
    else {
      var ch = ctx.cats.reduce(function (s, u) { return s + hpPct(u); }, 0);
      var rh = ctx.rats.reduce(function (s, u) { return s + hpPct(u); }, 0);
      win = ch > rh * 1.15;
    }
    push(ctx, { t: 'end', win: win, ticks: ctx.tickCount, turns: ctx.turnNo });
    return {
      win: win, ticks: ctx.tickCount, turns: ctx.turnNo, events: ctx.ev,
      catsAlive: catsAlive, ratsAlive: ratsAlive,
      catHpPct: ctx.cats.reduce(function (s, u) { return s + hpPct(u); }, 0) / ctx.cats.length,
      stats: ctx.cats.map(function (u) {
        return { uid: u.uid, name: u.title, dealt: u.stats.dealt, healed: u.stats.healed, taken: u.stats.taken, kills: u.stats.kills, crits: u.stats.crits, alive: !u.dead };
      })
    };
  };

  /* ------------------------------ 编队相关 ------------------------------ */
  function unitPower(u) {
    var a = effAtk(u);
    return u.maxHp * (1 + effDef(u) / DEF_K) * 0.55 + a * 9 + effSpd(u) * 6 + a * 14 * effCrit(u);
  }
  M3.unitPower = unitPower;

  M3.pickBalancedTeam = function (pool, n, rnd, opts) {
    n = n || 4;
    opts = opts || {};
    var r = rnd || Math.random;
    var lv = opts.level || 10;
    var cvMax = opts.cvMax === undefined ? 0.3 : opts.cvMax;
    var powers = pool.map(function (d) { return unitPower(M3.makeUnit(d, lv, 'cat')); });
    var cands = [];
    for (var iter = 0; iter < 500; iter++) {
      var idx = [], used = {};
      while (idx.length < n) {
        var i = Math.floor(r() * powers.length);
        if (used[i]) continue;
        used[i] = 1; idx.push(i);
      }
      var ps = idx.map(function (x) { return powers[x]; });
      var mean = ps.reduce(function (a, b) { return a + b; }, 0) / n;
      var sd = Math.sqrt(ps.reduce(function (a, b) { return a + Math.pow(b - mean, 2); }, 0) / n);
      var cv = sd / mean;
      if (cv > cvMax) continue;
      var roles = {}, dup = 0;
      idx.forEach(function (x) { if (roles[pool[x].role]) dup++; roles[pool[x].role] = 1; });
      cands.push({ idx: idx, cv: cv, dup: dup });
    }
    if (!cands.length) return pool.slice(0, n);
    var minDup = Math.min.apply(null, cands.map(function (c) { return c.dup; }));
    var pool2 = cands.filter(function (c) { return c.dup <= minDup + 1; });
    var pick = pool2[Math.floor(r() * pool2.length)];
    return pick.idx.map(function (i2) { return pool[i2]; });
  };

  M3.rollEnemyTeam = function (level, count, rnd, pool) {
    var r = rnd || Math.random;
    pool = pool || M3.mice;
    var out = [];
    for (var i = 0; i < count; i++) out.push({ def: pool[Math.floor(r() * pool.length)], level: level });
    return out;
  };

  M3.buildUnits = function (teamSpecs, side) {
    return teamSpecs.map(function (t) {
      if (t.uid) return t;
      return M3.makeUnit(t.def || t, t.level || 10, side);
    });
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = M3;
})(typeof window !== 'undefined' ? window : globalThis);
