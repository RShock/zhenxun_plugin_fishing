/* ==========================================================================
 * map3 · 猫鼠远洋 —— 角色数据（整数化 · 技能随等级成长）
 * --------------------------------------------------------------------------
 * 【数值规则】
 *  1. 角色所有数据（HP/ATK/DEF/SPD/暴击/技能数值）**一律整数**：
 *     - 属性：stat(L) = round(基础值 × (1 + 成长率 × (L-1)))，逐级四舍五入成整数
 *     - 暴击：整数百分比，每 4 级 +1%（L1 基础 → L5 +1 → L9 +2 → L13 +3 → L17 +4）
 *     - 技能：整数百分点，数值(L) = 基础 + 每级增量 × (L-1)，可设上限；不产生小数
 *  2. 技能随等级成长：4 个技能槽（被动1/大招1/被动2/大招2）在 L1/L5/L10/L15 逐个解锁，
 *     解锁后每级都会继续增强（被动与主动同等对待）。
 *  3. 技能数值一律写成整数百分点（60 = 60%），引擎内部再折算为系数；
 *     界面上永远只出现整数，不会出现 0.6 这类小数。
 * ========================================================================== */
(function (root) {
  var M3 = (root.M3 = root.M3 || {});

  /* ------------------------------ 成长基准 ------------------------------ */
  M3.growth = {
    hp: 0.105,   // L20 ≈ L1 × 2.99
    atk: 0.090,  // L20 ≈ L1 × 2.71
    def: 0.085,  // L20 ≈ L1 × 2.61
    spd: 0.050,  // L20 ≈ L1 × 1.95
    critStep: 4  // 每 4 级暴击 +1%
  };

  /* 数值规格：number 直接使用；{b,i,cap} = 基础 + 每级增量×（L-1），不超过上限 */
  M3.resolve = function (spec, lv) {
    if (spec === undefined || spec === null) return 0;
    if (typeof spec === 'number') return spec;
    if (typeof spec === 'string') return spec; /* 由调用方按键查找 */
    var v = spec.b + (spec.i || 0) * (lv - 1);
    if (spec.cap !== undefined) v = Math.min(spec.cap, v);
    return v;
  };
  M3.frac = function (spec, lv) { return M3.resolve(spec, lv) / 100; };

  /* 属性表：逐级四舍五入，保证每个等级都是整数 */
  M3.statAt = function (base, lv) {
    var g = M3.growth, k = lv - 1;
    return {
      hp: Math.round(base.hp * (1 + g.hp * k)),
      atk: Math.round(base.atk * (1 + g.atk * k)),
      def: Math.round(base.def * (1 + g.def * k)),
      spd: Math.round(base.spd * (1 + g.spd * k)),
      crit: base.crit + Math.floor(k / g.critStep)      /* 整数百分点 */
    };
  };
  /* 完整 1~20 级属性表（展示 / 自检用） */
  M3.statTable = function (def) {
    var rows = [];
    for (var lv = 1; lv <= 20; lv++) rows.push(Object.assign({ lv: lv }, M3.statAt(def.base, lv)));
    return rows;
  };

  /* --------------------------------------------------------------------------
   * 我方 10 名猫猫（基础值全整数；技能数值为整数百分点，随等级成长）
   * ------------------------------------------------------------------------ */
  var CATS = [
    {
      id: 'cat_tuffy', name: '塔菲', title: '橘座·舰长', role: '守护', color: '#f0a132',
      base: { hp: 82, atk: 9, def: 10, spd: 8, crit: 4 },
      passives: [
        {
          id: 'p1', name: '旗舰护航', unlock: 1,
          vals: { mul: { b: 80, i: 2, cap: 130 }, turns: 2 },
          tmpl: '战斗开始时为全体队友提供自身攻击 <b>{mul}%</b> 的护盾（{turns} 回合）。',
          triggers: [{ on: 'onBattleStart', effect: { kind: 'shield', mul: '%mul', target: 'allAllies', turns: 2 } }]
        },
        {
          id: 'p2', name: '铁骨舱壁', unlock: 10,
          vals: { res: { b: 12, i: 1, cap: 25 }, thr: { b: 50, i: 0 }, defUp: { b: 25, i: 1, cap: 40 } },
          tmpl: '受到伤害降低 <b>{res}%</b>；自身生命低于 {thr}% 时防御 <b>+{defUp}%</b>。',
          stat: { dmgTaken: '%res' },
          dyn: [{ c: 'selfHpBelow', v: 50, mod: { defPct: '%defUp' } }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '锚定站位', cost: 50, unlock: 5, ai: { prio: 3 },
          vals: { mul: { b: 60, i: 3, cap: 117 }, defUp: { b: 30, i: 1, cap: 49 }, turns: 2 },
          tmpl: '对全体敌人造成 <b>{mul}%</b> 攻击的伤害；自身嘲讽 {turns} 回合、防御 <b>+{defUp}%</b>。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'status', status: 'taunt', turns: '%turns', target: 'self' },
            { kind: 'status', status: 'defUp', value: '%defUp', turns: '%turns', target: 'self' }
          ]
        },
        {
          id: 'u2', name: '舰长怒吼', cost: 80, unlock: 15, ai: { prio: 3 },
          vals: { atkUp: { b: 25, i: 1, cap: 44 }, heal: { b: 50, i: 2, cap: 88 }, turns: 3 },
          tmpl: '全体队友攻击 <b>+{atkUp}%</b>（{turns} 回合），并回复自身攻击 <b>{heal}%</b> 的生命。',
          steps: [
            { kind: 'status', status: 'atkUp', value: '%atkUp', turns: '%turns', target: 'allAllies' },
            { kind: 'heal', mul: '%heal', target: 'allAllies' }
          ]
        }
      ]
    },
    {
      id: 'cat_mia', name: '米娅', title: '白爪·医官', role: '治疗', color: '#7fc8f8',
      base: { hp: 64, atk: 8, def: 7, spd: 10, crit: 5 },
      passives: [
        {
          id: 'p1', name: '随行药箱', unlock: 1,
          vals: { mul: { b: 35, i: 2, cap: 70 } },
          tmpl: '每回合结束时治疗生命百分比最低的队友，量为自身攻击的 <b>{mul}%</b>。',
          triggers: [{ on: 'onTurnEnd', effect: { kind: 'heal', mul: '%mul', target: 'lowestAlly' } }]
        },
        {
          id: 'p2', name: '无菌手套', unlock: 10,
          vals: { up: { b: 20, i: 1, cap: 35 } },
          tmpl: '全体队友受到的治疗效果 <b>+{up}%</b>。',
          stat: { healUp: '%up' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '急救喷雾', cost: 50, unlock: 5, ai: { prio: 6, cond: { c: 'allyHpBelow', v: 70 } },
          vals: { mul: { b: 160, i: 5, cap: 255 }, count: 1 },
          tmpl: '治疗生命最低的队友（自身攻击 <b>{mul}%</b>），并清除其 {count} 个负面状态。',
          steps: [
            { kind: 'heal', mul: '%mul', target: 'lowestAlly' },
            { kind: 'cleanse', count: 1, target: 'lowestAlly' }
          ]
        },
        {
          id: 'u2', name: '净化之泉', cost: 80, unlock: 15, ai: { prio: 5, cond: { c: 'allyHpBelow', v: 60 } },
          vals: { mul: { b: 110, i: 4, cap: 186 }, regen: { b: 30, i: 1, cap: 49 }, turns: 2 },
          tmpl: '治疗全体队友自身攻击 <b>{mul}%</b> 的生命，并附加 {turns} 回合回春（每回合 {regen}%）。',
          steps: [
            { kind: 'heal', mul: '%mul', target: 'allAllies' },
            { kind: 'dot', id: 'regen', mul: '%regen', turns: '%turns', target: 'allAllies' }
          ]
        }
      ]
    },
    {
      id: 'cat_shadow', name: '影爪', title: '黑尾·夜刃', role: '爆发', color: '#8e7cf0',
      base: { hp: 58, atk: 14, def: 5, spd: 12, crit: 15 },
      passives: [
        {
          id: 'p1', name: '暗夜猎手', unlock: 1,
          vals: { thr: { b: 40, i: 1, cap: 55 }, bonus: { b: 35, i: 1, cap: 55 } },
          tmpl: '对生命低于 {thr}% 的敌人造成伤害 <b>+{bonus}%</b>。',
          triggers: [{
            on: 'onBeforeDamage', cond: { c: 'targetHpBelow', v: '%thr' },
            effect: { kind: 'damageMod', value: '%bonus' }
          }]
        },
        {
          id: 'p2', name: '致命一击', unlock: 10,
          vals: { crit: { b: 10, i: 1, cap: 25 }, cdmg: { b: 30, i: 2, cap: 60 } },
          tmpl: '暴击率 <b>+{crit}%</b>，暴击伤害 <b>+{cdmg}%</b>。',
          stat: { critAdd: '%crit', critDmgAdd: '%cdmg' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '三步连斩', cost: 50, unlock: 5, ai: { prio: 4 },
          vals: { mul: { b: 60, i: 2, cap: 98 }, hits: 3 },
          tmpl: '对单体造成 {hits} 段 <b>{mul}%</b> 攻击的伤害，每段独立判定暴击。',
          steps: [{ kind: 'damage', mul: '%mul', hits: 3, target: 'one' }]
        },
        {
          id: 'u2', name: '背刺处决', cost: 80, unlock: 15, ai: { prio: 5 },
          vals: { mul: { b: 240, i: 6, cap: 354 }, thr: { b: 35, i: 1, cap: 54 }, bonus: { b: 60, i: 2, cap: 98 } },
          tmpl: '对单体造成 <b>{mul}%</b> 伤害；目标生命低于 {thr}% 时伤害再 <b>+{bonus}%</b>。',
          steps: [{ kind: 'damage', mul: '%mul', target: 'one', execute: { below: '%thr', bonus: '%bonus' } }]
        }
      ]
    },
    {
      id: 'cat_macchiato', name: '玛奇朵', title: '布偶·炮手', role: '群攻', color: '#e88fb0',
      base: { hp: 60, atk: 13, def: 5, spd: 9, crit: 7 },
      passives: [
        {
          id: 'p1', name: '重装弹链', unlock: 1,
          vals: { up: { b: 6, i: 1, cap: 15 }, max: 5 },
          tmpl: '每次造成伤害后自身攻击 <b>+{up}%</b>，最多叠加 {max} 层。',
          triggers: [{
            on: 'onAttack', stackMaxBy: 'max',
            effect: { kind: 'status', status: 'atkUp', value: '%up', turns: 99, target: 'self', stackMax: 5 }
          }]
        },
        {
          id: 'p2', name: '散弹装填', unlock: 10,
          vals: { chance: { b: 40, i: 1, cap: 60 }, mul: { b: 70, i: 2, cap: 108 } },
          tmpl: '普攻有 <b>{chance}%</b> 几率改为对全体敌人造成 {mul}% 攻击的伤害。',
          triggerSpecial: { kind: 'spread', chanceKey: 'chance', mulKey: 'mul', chanceVal: { b: 40, i: 1, cap: 60 }, mulVal: { b: 70, i: 2, cap: 108 } }
        }
      ],
      ults: [
        {
          id: 'u1', name: '齐射', cost: 50, unlock: 5, ai: { prio: 4, cond: { c: 'enemyCountGE', v: 3 } },
          vals: { mul: { b: 85, i: 3, cap: 142 } },
          tmpl: '对全体敌人造成 <b>{mul}%</b> 攻击的伤害。',
          steps: [{ kind: 'damage', mul: '%mul', target: 'all' }]
        },
        {
          id: 'u2', name: '饱和轰炸', cost: 80, unlock: 15, ai: { prio: 5 },
          vals: { mul: { b: 125, i: 4, cap: 201 }, defDown: { b: 20, i: 1, cap: 39 }, turns: 2 },
          tmpl: '对全体敌人造成 <b>{mul}%</b> 伤害，并使其防御 <b>-{defDown}%</b>（{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'status', status: 'defDown', value: '%defDown', turns: '%turns', target: 'all' }
          ]
        }
      ]
    },
    {
      id: 'cat_abao', name: '阿豹', title: '狸花·督头', role: '指挥', color: '#c9a227',
      base: { hp: 66, atk: 10, def: 7, spd: 11, crit: 6 },
      passives: [
        {
          id: 'p1', name: '战吼', unlock: 1,
          vals: { up: { b: 12, i: 1, cap: 25 } },
          tmpl: '战斗开始时全体队友攻击 <b>+{up}%</b>。',
          triggers: [{ on: 'onBattleStart', effect: { kind: 'status', status: 'atkUp', value: '%up', turns: 99, target: 'allAllies' } }]
        },
        {
          id: 'p2', name: '甲板指挥', unlock: 10,
          vals: { amount: { b: 8, i: 1, cap: 18 } },
          tmpl: '每回合开始时为能量最低的队友充能 <b>+{amount}</b> 点。',
          triggers: [{ on: 'onTurnStart', effect: { kind: 'energy', amount: '%amount', target: 'lowestEnergyAlly' } }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '压制射击', cost: 50, unlock: 5, ai: { prio: 3 },
          vals: { mul: { b: 110, i: 3, cap: 167 }, atkDown: { b: 25, i: 1, cap: 44 }, turns: 2 },
          tmpl: '对攻击最高的敌人造成 <b>{mul}%</b> 伤害，并使其攻击 <b>-{atkDown}%</b>（{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'oneHighestAtk' },
            { kind: 'status', status: 'atkDown', value: '%atkDown', turns: '%turns', target: 'oneHighestAtk' }
          ]
        },
        {
          id: 'u2', name: '全力突击', cost: 80, unlock: 15, ai: { prio: 4, cond: { c: 'turnLE', v: 3 } },
          vals: { atkUp: { b: 30, i: 1, cap: 49 }, spdUp: { b: 20, i: 1, cap: 39 }, turns: 3 },
          tmpl: '全体队友攻击 <b>+{atkUp}%</b>、速度 <b>+{spdUp}%</b>（{turns} 回合）。',
          steps: [
            { kind: 'status', status: 'atkUp', value: '%atkUp', turns: '%turns', target: 'allAllies' },
            { kind: 'status', status: 'spdUp', value: '%spdUp', turns: '%turns', target: 'allAllies' }
          ]
        }
      ]
    },
    {
      id: 'cat_denguang', name: '电光', title: '暹罗·斥候', role: '连击', color: '#5fd3c4',
      base: { hp: 56, atk: 12, def: 5, spd: 15, crit: 10 },
      passives: [
        {
          id: 'p1', name: '猫步', unlock: 1,
          vals: { dodge: { b: 12, i: 1, cap: 25 } },
          tmpl: '闪避 <b>+{dodge}%</b>。',
          stat: { dodge: '%dodge' }
        },
        {
          id: 'p2', name: '连环爪', unlock: 10,
          vals: { chance: { b: 45, i: 1, cap: 65 }, mul: { b: 50, i: 1, cap: 78 } },
          tmpl: '普攻后有 <b>{chance}%</b> 几率追加一次 {mul}% 攻击的追击。',
          triggerSpecial: { kind: 'pursuit', chanceVal: { b: 45, i: 1, cap: 65 }, mulVal: { b: 50, i: 1, cap: 78 } }
        }
      ],
      ults: [
        {
          id: 'u1', name: '疾风突袭', cost: 50, unlock: 5, ai: { prio: 4 },
          vals: { mul: { b: 130, i: 3, cap: 187 } },
          tmpl: '对单体造成 <b>{mul}%</b> 伤害，并使自身立即获得一次额外行动。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'one' },
            { kind: 'haste', target: 'self' }
          ]
        },
        {
          id: 'u2', name: '残影乱舞', cost: 80, unlock: 15, ai: { prio: 5 },
          vals: { mul: { b: 70, i: 2, cap: 108 }, hits: 4, dodge: { b: 25, i: 1, cap: 44 }, turns: 2 },
          tmpl: '对随机敌人造成 {hits} 段 <b>{mul}%</b> 伤害，并获得 {turns} 回合闪避 <b>+{dodge}%</b>。',
          steps: [
            { kind: 'damage', mul: '%mul', hits: 4, target: 'random' },
            { kind: 'status', status: 'dodge', value: '%dodge', turns: '%turns', target: 'self' }
          ]
        }
      ]
    },
    {
      id: 'cat_anchor', name: '大副', title: '缅因·铁锚', role: '破防', color: '#9c8262',
      base: { hp: 74, atk: 12, def: 9, spd: 7, crit: 8 },
      passives: [
        {
          id: 'p1', name: '巨力', unlock: 1,
          vals: { atk: { b: 10, i: 1, cap: 20 }, pen: { b: 20, i: 1, cap: 35 } },
          tmpl: '攻击 <b>+{atk}%</b>，无视目标 <b>{pen}%</b> 防御。',
          stat: { atkPct: '%atk', defPen: '%pen' }
        },
        {
          id: 'p2', name: '压舱石', unlock: 10,
          vals: { res: { b: 8, i: 1, cap: 18 } },
          tmpl: '受到伤害降低 <b>{res}%</b>。',
          stat: { dmgTaken: '%res' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '碎甲重锤', cost: 50, unlock: 5, ai: { prio: 3 },
          vals: { mul: { b: 150, i: 4, cap: 226 }, defDown: { b: 30, i: 1, cap: 49 }, turns: 3 },
          tmpl: '对单体造成 <b>{mul}%</b> 伤害，并降低其 <b>{defDown}%</b> 防御（{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'one' },
            { kind: 'status', status: 'defDown', value: '%defDown', turns: '%turns', target: 'one' }
          ]
        },
        {
          id: 'u2', name: '一击必沉', cost: 80, unlock: 15, ai: { prio: 5 },
          vals: { mul: { b: 250, i: 6, cap: 364 }, chance: { b: 50, i: 1, cap: 69 }, turns: 1 },
          tmpl: '对单体造成 <b>{mul}%</b> 伤害，并有 {chance}% 几率晕眩 {turns} 回合。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'one' },
            { kind: 'status', status: 'stun', turns: '%turns', chance: '%chance', target: 'one' }
          ]
        }
      ]
    },
    {
      id: 'cat_gear', name: '齿轮', title: '三花·机械师', role: '持续伤害', color: '#f2803c',
      base: { hp: 62, atk: 11, def: 6, spd: 10, crit: 6 },
      passives: [
        {
          id: 'p1', name: '蒸汽锅炉', unlock: 1,
          vals: { burn: { b: 18, i: 1, cap: 35 }, turns: 2 },
          tmpl: '每次造成伤害后为目标附加 1 层灼烧（自身攻击 <b>{burn}%</b>，{turns} 回合）。',
          triggers: [{ on: 'onAttack', effect: { kind: 'dot', id: 'burn', mul: '%burn', turns: 2, target: 'lastHit' } }]
        },
        {
          id: 'p2', name: '自动扳手', unlock: 10,
          vals: { burn: { b: 18, i: 1, cap: 35 }, turns: 2 },
          tmpl: '每回合结束时为随机一名敌人附加 1 层灼烧（自身攻击 <b>{burn}%</b>，{turns} 回合）。',
          triggers: [{ on: 'onTurnEnd', effect: { kind: 'dot', id: 'burn', mul: '%burn', turns: 2, target: 'randomEnemy' } }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '燃油喷射', cost: 50, unlock: 5, ai: { prio: 4 },
          vals: { mul: { b: 70, i: 3, cap: 127 }, burn: { b: 30, i: 1, cap: 49 }, turns: 2 },
          tmpl: '对全体敌人造成 <b>{mul}%</b> 伤害，并附加灼烧（自身攻击 {burn}%，{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'dot', id: 'burn', mul: '%burn', turns: '%turns', target: 'all' }
          ]
        },
        {
          id: 'u2', name: '过载核心', cost: 80, unlock: 15, ai: { prio: 5, cond: { c: 'enemiesWithDot' } },
          vals: { mul: { b: 160, i: 4, cap: 236 }, boost: { b: 50, i: 2, cap: 88 }, max: 3 },
          tmpl: '对单体造成 <b>{mul}%</b> 伤害，并引爆其灼烧（每层额外造成自身攻击 {boost}%，最多 {max} 层）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'one' },
            { kind: 'detonate', dotId: 'burn', mul: '%boost', maxStacks: 3, target: 'one' }
          ]
        }
      ]
    },
    {
      id: 'cat_sherry', name: '雪莉', title: '银渐·炮术长', role: '控制', color: '#a8c6e8',
      base: { hp: 60, atk: 12, def: 6, spd: 10, crit: 8 },
      passives: [
        {
          id: 'p1', name: '元素充能', unlock: 1,
          vals: { amount: { b: 12, i: 1, cap: 25 } },
          tmpl: '暴击时回复 <b>{amount}</b> 点能量。',
          triggers: [{ on: 'onCrit', effect: { kind: 'energy', amount: '%amount', target: 'self' } }]
        },
        {
          id: 'p2', name: '霜之护盾', unlock: 10,
          vals: { thr: { b: 60, i: 1, cap: 75 }, mul: { b: 70, i: 2, cap: 110 } },
          tmpl: '生命首次低于 {thr}% 时获得自身攻击 <b>{mul}%</b> 的护盾。',
          triggers: [{
            on: 'onTurnStart', once: true, cond: { c: 'selfHpBelow', v: '%thr' },
            effect: { kind: 'shield', mul: '%mul', target: 'self', turns: 99 }
          }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '冰锥散射', cost: 50, unlock: 5, ai: { prio: 4 },
          vals: { mul: { b: 75, i: 3, cap: 132 }, chance: { b: 35, i: 1, cap: 54 }, turns: 1 },
          tmpl: '对全体敌人造成 <b>{mul}%</b> 伤害，{chance}% 几率冰冻 {turns} 回合。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'status', status: 'stun', turns: '%turns', chance: '%chance', target: 'all' }
          ]
        },
        {
          id: 'u2', name: '暴风雪', cost: 80, unlock: 15, ai: { prio: 5 },
          vals: { mul: { b: 115, i: 4, cap: 191 }, bonus: { b: 25, i: 1, cap: 44 }, spdDown: { b: 25, i: 1, cap: 44 }, turns: 2 },
          tmpl: '对全体敌人造成 <b>{mul}%</b> 伤害（对被冰冻者再 +{bonus}%），并降低 {spdDown}% 速度（{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all', bonusVsStunned: '%bonus' },
            { kind: 'status', status: 'spdDown', value: '%spdDown', turns: '%turns', target: 'all' }
          ]
        }
      ]
    },
    {
      id: 'cat_pudding', name: '布丁', title: '奶牛·水手长', role: '吸血', color: '#6f7bd6',
      base: { hp: 78, atk: 12, def: 8, spd: 9, crit: 9 },
      passives: [
        {
          id: 'p1', name: '嗜血', unlock: 1,
          vals: { ls: { b: 18, i: 1, cap: 35 } },
          tmpl: '造成伤害的 <b>{ls}%</b> 回复自身生命。',
          stat: { lifesteal: '%ls' }
        },
        {
          id: 'p2', name: '背水一战', unlock: 10,
          vals: { per: { b: 6, i: 1, cap: 10 }, max: { b: 48, i: 2, cap: 80 } },
          tmpl: '每损失 10% 生命攻击 <b>+{per}%</b>（最多 +{max}%）。',
          stat: { rampAtk: ['%per', '%max'] }
        }
      ],
      ults: [
        {
          id: 'u1', name: '利爪连击', cost: 50, unlock: 5, ai: { prio: 4 },
          vals: { mul: { b: 55, i: 2, cap: 93 }, hits: 3, ls: { b: 25, i: 1, cap: 44 } },
          tmpl: '对单体造成 {hits} 段 <b>{mul}%</b> 伤害，每段按伤害的 {ls}% 回复自身。',
          steps: [{ kind: 'damage', mul: '%mul', hits: 3, target: 'one', lifesteal: '%ls' }]
        },
        {
          id: 'u2', name: '狂澜', cost: 80, unlock: 15, ai: { prio: 5 },
          vals: { mul: { b: 100, i: 4, cap: 176 }, ls: { b: 30, i: 1, cap: 49 } },
          tmpl: '对全体敌人造成 <b>{mul}%</b> 伤害，并按总伤害的 {ls}% 回复自身。',
          steps: [{ kind: 'damage', mul: '%mul', target: 'all', lifesteal: '%ls' }]
        }
      ]
    }
  ];

  /* --------------------------------------------------------------------------
   * 敌方 10 名老鼠杂兵（同一套系统；基础值已含"杂兵强度 ≈ 同级猫的 92%"）
   * ------------------------------------------------------------------------ */
  var MICE = [
    {
      id: 'rat_gear', name: '齿轮鼠·工兵', role: '近战', color: '#9aa4b2',
      base: { hp: 71, atk: 8, def: 6, spd: 8, crit: 4 },
      passives: [
        {
          id: 'p1', name: '流水线', unlock: 1,
          vals: { chance: { b: 20, i: 1, cap: 35 }, mul: { b: 50, i: 1, cap: 78 } },
          tmpl: '受到伤害后 {chance}% 几率反击 {mul}% 攻击的伤害。',
          triggers: [{
            on: 'onTakeDamage', chanceVal: { b: 20, i: 1, cap: 35 },
            effect: { kind: 'damage', mul: '%mul', target: 'attacker' }
          }]
        },
        {
          id: 'p2', name: '标准件', unlock: 10,
          vals: { atk: { b: 8, i: 1, cap: 18 } },
          tmpl: '攻击 <b>+{atk}%</b>。',
          stat: { atkPct: '%atk' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '扳手敲击', cost: 50, unlock: 5, ai: { prio: 3 },
          vals: { mul: { b: 130, i: 2, cap: 168 } },
          tmpl: '对单体造成 <b>{mul}%</b> 伤害。',
          steps: [{ kind: 'damage', mul: '%mul', target: 'one' }]
        },
        {
          id: 'u2', name: '冲压机', cost: 80, unlock: 15, ai: { prio: 4 },
          vals: { mul: { b: 190, i: 3, cap: 247 }, cost: { b: 6, i: 0 } },
          tmpl: '对单体造成 <b>{mul}%</b> 伤害，自身承受最大生命 {cost}% 的损耗。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'one' },
            { kind: 'selfHpCost', v: '%cost', target: 'self' }
          ]
        }
      ]
    },
    {
      id: 'rat_chimney', name: '烟囱鼠·炉工', role: '灼烧', color: '#8a6b5a',
      base: { hp: 67, atk: 8, def: 5, spd: 7, crit: 5 },
      passives: [
        {
          id: 'p1', name: '余烬', unlock: 1,
          vals: { burn: { b: 12, i: 1, cap: 26 }, turns: 2 },
          tmpl: '每次造成伤害后附加灼烧（自身攻击 <b>{burn}%</b>，{turns} 回合）。',
          triggers: [{ on: 'onAttack', effect: { kind: 'dot', id: 'burn', mul: '%burn', turns: 2, target: 'lastHit' } }]
        },
        {
          id: 'p2', name: '耐火砖', unlock: 10,
          vals: { res: { b: 8, i: 1, cap: 18 } },
          tmpl: '受到伤害降低 <b>{res}%</b>。',
          stat: { dmgTaken: '%res' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '喷焰', cost: 50, unlock: 5, ai: { prio: 4 },
          vals: { mul: { b: 60, i: 2, cap: 98 }, burn: { b: 18, i: 1, cap: 35 }, turns: 2 },
          tmpl: '对全体造成 <b>{mul}%</b> 伤害并附加灼烧（自身攻击 {burn}%，{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'dot', id: 'burn', mul: '%burn', turns: '%turns', target: 'all' }
          ]
        },
        {
          id: 'u2', name: '煤渣爆燃', cost: 80, unlock: 15, ai: { prio: 4 },
          vals: { mul: { b: 80, i: 3, cap: 137 }, atkDown: { b: 15, i: 1, cap: 29 }, turns: 2 },
          tmpl: '对全体造成 <b>{mul}%</b> 伤害并使其攻击 <b>-{atkDown}%</b>（{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'status', status: 'atkDown', value: '%atkDown', turns: '%turns', target: 'all' }
          ]
        }
      ]
    },
    {
      id: 'rat_oil', name: '油污鼠·技师', role: '减益', color: '#7d8a6a',
      base: { hp: 69, atk: 8, def: 6, spd: 8, crit: 4 },
      passives: [
        {
          id: 'p1', name: '油滑', unlock: 1,
          vals: { dodge: { b: 8, i: 1, cap: 18 } },
          tmpl: '闪避 <b>+{dodge}%</b>。',
          stat: { dodge: '%dodge' }
        },
        {
          id: 'p2', name: '润滑', unlock: 10,
          vals: { spd: { b: 10, i: 1, cap: 20 } },
          tmpl: '速度 <b>+{spd}%</b>。',
          stat: { spdPct: '%spd' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '泼油', cost: 50, unlock: 5, ai: { prio: 3 },
          vals: { mul: { b: 90, i: 2, cap: 128 }, atkDown: { b: 20, i: 1, cap: 39 }, turns: 2 },
          tmpl: '对攻击最高的敌人造成 <b>{mul}%</b> 伤害并降低其 {atkDown}% 攻击（{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'oneHighestAtk' },
            { kind: 'status', status: 'atkDown', value: '%atkDown', turns: '%turns', target: 'oneHighestAtk' }
          ]
        },
        {
          id: 'u2', name: '油污爆燃', cost: 80, unlock: 15, ai: { prio: 4 },
          vals: { mul: { b: 70, i: 3, cap: 127 }, spdDown: { b: 20, i: 1, cap: 39 }, turns: 2 },
          tmpl: '对全体造成 <b>{mul}%</b> 伤害并降低 {spdDown}% 速度（{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'status', status: 'spdDown', value: '%spdDown', turns: '%turns', target: 'all' }
          ]
        }
      ]
    },
    {
      id: 'rat_shield', name: '铁屑鼠·盾卫', role: '坦克', color: '#8f9aa8',
      base: { hp: 82, atk: 7, def: 8, spd: 6, crit: 3 },
      passives: [
        {
          id: 'p1', name: '废铁外壳', unlock: 1,
          vals: { res: { b: 10, i: 1, cap: 22 } },
          tmpl: '受到伤害降低 <b>{res}%</b>。',
          stat: { dmgTaken: '%res' }
        },
        {
          id: 'p2', name: '拾荒', unlock: 10,
          vals: { mul: { b: 15, i: 1, cap: 29 } },
          tmpl: '每回合开始回复自身攻击 <b>{mul}%</b> 的生命。',
          triggers: [{ on: 'onTurnStart', effect: { kind: 'heal', mul: '%mul', target: 'self' } }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '铁盾冲撞', cost: 50, unlock: 5, ai: { prio: 2 },
          vals: { mul: { b: 90, i: 2, cap: 128 }, defUp: { b: 25, i: 1, cap: 44 }, turns: 2 },
          tmpl: '对攻击最高的敌人造成 <b>{mul}%</b> 伤害，自身嘲讽 {turns} 回合、防御 +{defUp}%。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'oneHighestAtk' },
            { kind: 'status', status: 'taunt', turns: '%turns', target: 'self' },
            { kind: 'status', status: 'defUp', value: '%defUp', turns: '%turns', target: 'self' }
          ]
        },
        {
          id: 'u2', name: '磁力壁垒', cost: 80, unlock: 15, ai: { prio: 4 },
          vals: { mul: { b: 90, i: 2, cap: 128 }, turns: 2 },
          tmpl: '为全体队友提供自身攻击 <b>{mul}%</b> 的护盾（{turns} 回合）。',
          steps: [{ kind: 'shield', mul: '%mul', target: 'allAllies', turns: 2 }]
        }
      ]
    },
    {
      id: 'rat_spring', name: '弹簧鼠·突袭兵', role: '连击', color: '#b58fb0',
      base: { hp: 63, atk: 8, def: 5, spd: 12, crit: 8 },
      passives: [
        {
          id: 'p1', name: '弹簧腿', unlock: 1,
          vals: { chance: { b: 30, i: 1, cap: 45 }, mul: { b: 50, i: 1, cap: 78 } },
          tmpl: '普攻有 <b>{chance}%</b> 几率追加 {mul}% 攻击的伤害。',
          triggerSpecial: { kind: 'pursuit', chanceVal: { b: 30, i: 1, cap: 45 }, mulVal: { b: 50, i: 1, cap: 78 } }
        },
        {
          id: 'p2', name: '弹跳', unlock: 10,
          vals: { dodge: { b: 6, i: 1, cap: 15 } },
          tmpl: '闪避 <b>+{dodge}%</b>。',
          stat: { dodge: '%dodge' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '弹射突袭', cost: 50, unlock: 5, ai: { prio: 3 },
          vals: { mul: { b: 65, i: 2, cap: 103 }, hits: 2 },
          tmpl: '对单体造成 {hits} 段 <b>{mul}%</b> 伤害。',
          steps: [{ kind: 'damage', mul: '%mul', hits: 2, target: 'one' }]
        },
        {
          id: 'u2', name: '连环弹射', cost: 80, unlock: 15, ai: { prio: 4 },
          vals: { mul: { b: 75, i: 2, cap: 113 }, hits: 3 },
          tmpl: '对随机敌人造成 {hits} 段 <b>{mul}%</b> 伤害。',
          steps: [{ kind: 'damage', mul: '%mul', hits: 3, target: 'random' }]
        }
      ]
    },
    {
      id: 'rat_sewer', name: '污水鼠·投手', role: '毒伤', color: '#6f9a7a',
      base: { hp: 67, atk: 8, def: 5, spd: 7, crit: 4 },
      passives: [
        {
          id: 'p1', name: '污染物', unlock: 1,
          vals: { poison: { b: 10, i: 1, cap: 24 }, turns: 2 },
          tmpl: '造成伤害后附加中毒（自身攻击 <b>{poison}%</b>，{turns} 回合）。',
          triggers: [{ on: 'onAttack', effect: { kind: 'dot', id: 'poison', mul: '%poison', turns: 2, target: 'lastHit' } }]
        },
        {
          id: 'p2', name: '防腐皮', unlock: 10,
          vals: { res: { b: 30, i: 1, cap: 48 } },
          tmpl: '受到的中毒与灼烧伤害降低 <b>{res}%</b>。',
          stat: { dotTaken: '-%res' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '污水弹', cost: 50, unlock: 5, ai: { prio: 4 },
          vals: { mul: { b: 55, i: 2, cap: 93 }, poison: { b: 15, i: 1, cap: 32 }, turns: 2 },
          tmpl: '对全体造成 <b>{mul}%</b> 伤害并附加中毒（自身攻击 {poison}%，{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'dot', id: 'poison', mul: '%poison', turns: '%turns', target: 'all' }
          ]
        },
        {
          id: 'u2', name: '下水道洪流', cost: 80, unlock: 15, ai: { prio: 4 },
          vals: { mul: { b: 80, i: 3, cap: 137 }, poison: { b: 20, i: 1, cap: 39 }, turns: 2 },
          tmpl: '对全体造成 <b>{mul}%</b> 伤害并附加中毒（自身攻击 {poison}%，{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'dot', id: 'poison', mul: '%poison', turns: '%turns', target: 'all' }
          ]
        }
      ]
    },
    {
      id: 'rat_wrench', name: '扳手鼠·修理工', role: '治疗', color: '#c2a06a',
      base: { hp: 69, atk: 7, def: 6, spd: 8, crit: 3 },
      passives: [
        {
          id: 'p1', name: '备用零件', unlock: 1,
          vals: { mul: { b: 22, i: 1, cap: 41 } },
          tmpl: '每回合结束治疗生命最低的队友（自身攻击 <b>{mul}%</b>）。',
          triggers: [{ on: 'onTurnEnd', effect: { kind: 'heal', mul: '%mul', target: 'lowestAlly' } }]
        },
        {
          id: 'p2', name: '组装', unlock: 10,
          vals: { up: { b: 10, i: 1, cap: 20 } },
          tmpl: '全体队友受到的治疗 <b>+{up}%</b>。',
          stat: { healUp: '%up' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '紧急维修', cost: 50, unlock: 5, ai: { prio: 6, cond: { c: 'allyHpBelow', v: 70 } },
          vals: { mul: { b: 110, i: 4, cap: 186 } },
          tmpl: '治疗生命最低的队友（自身攻击 <b>{mul}%</b>）。',
          steps: [{ kind: 'heal', mul: '%mul', target: 'lowestAlly' }]
        },
        {
          id: 'u2', name: '流水线检修', cost: 80, unlock: 15, ai: { prio: 5, cond: { c: 'allyHpBelow', v: 65 } },
          vals: { mul: { b: 70, i: 3, cap: 127 }, count: 1 },
          tmpl: '治疗全体队友（自身攻击 <b>{mul}%</b>）并清除 {count} 个负面状态。',
          steps: [
            { kind: 'heal', mul: '%mul', target: 'allAllies' },
            { kind: 'cleanse', count: 1, target: 'allAllies' }
          ]
        }
      ]
    },
    {
      id: 'rat_powder', name: '火药鼠·爆破手', role: '爆发', color: '#d08050',
      base: { hp: 63, atk: 9, def: 4, spd: 9, crit: 10 },
      passives: [
        {
          id: 'p1', name: '不稳定火药', unlock: 1,
          vals: { taken: { b: 5, i: 0 }, crit: { b: 8, i: 1, cap: 20 } },
          tmpl: '自身受到伤害 <b>+{taken}%</b>，暴击率 <b>+{crit}%</b>。',
          stat: { dmgTaken: '%taken', critAdd: '%crit' }
        },
        {
          id: 'p2', name: '引信', unlock: 10,
          vals: { thr: { b: 50, i: 1, cap: 65 }, bonus: { b: 15, i: 1, cap: 29 } },
          tmpl: '攻击生命低于 {thr}% 的目标时伤害 <b>+{bonus}%</b>。',
          triggers: [{
            on: 'onBeforeDamage', cond: { c: 'targetHpBelow', v: '%thr' },
            effect: { kind: 'damageMod', value: '%bonus' }
          }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '炸药包', cost: 50, unlock: 5, ai: { prio: 3 },
          vals: { mul: { b: 170, i: 3, cap: 227 }, cost: { b: 7, i: 0 } },
          tmpl: '对单体造成 <b>{mul}%</b> 伤害，自身承受最大生命 {cost}% 的损耗。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'one' },
            { kind: 'selfHpCost', v: '%cost', target: 'self' }
          ]
        },
        {
          id: 'u2', name: '连环爆破', cost: 80, unlock: 15, ai: { prio: 4 },
          vals: { mul: { b: 90, i: 3, cap: 147 }, cost: { b: 10, i: 0 } },
          tmpl: '对全体造成 <b>{mul}%</b> 伤害，自身承受最大生命 {cost}% 的损耗。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'selfHpCost', v: '%cost', target: 'self' }
          ]
        }
      ]
    },
    {
      id: 'rat_turbo', name: '涡轮鼠·飞轮兵', role: '增速', color: '#7fa8c9',
      base: { hp: 65, atk: 8, def: 5, spd: 11, crit: 6 },
      passives: [
        {
          id: 'p1', name: '涡轮', unlock: 1,
          vals: { up: { b: 3, i: 1, cap: 9 }, max: 8 },
          tmpl: '每回合开始速度 <b>+{up}%</b>（最多叠加 {max} 层）。',
          triggers: [{
            on: 'onTurnStart',
            effect: { kind: 'status', status: 'spdUp', value: '%up', turns: 99, target: 'self', stackMax: 8 }
          }]
        },
        {
          id: 'p2', name: '离心', unlock: 10,
          vals: { res: { b: 6, i: 1, cap: 15 } },
          tmpl: '受到伤害降低 <b>{res}%</b>。',
          stat: { dmgTaken: '%res' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '高速切割', cost: 50, unlock: 5, ai: { prio: 3 },
          vals: { mul: { b: 110, i: 2, cap: 148 }, spdUp: { b: 20, i: 1, cap: 39 }, turns: 2 },
          tmpl: '对单体造成 <b>{mul}%</b> 伤害，并使自身速度 +{spdUp}%（{turns} 回合）。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'one' },
            { kind: 'status', status: 'spdUp', value: '%spdUp', turns: '%turns', target: 'self' }
          ]
        },
        {
          id: 'u2', name: '旋风乱斩', cost: 80, unlock: 15, ai: { prio: 4 },
          vals: { mul: { b: 70, i: 2, cap: 108 }, hits: 3 },
          tmpl: '对随机敌人造成 {hits} 段 <b>{mul}%</b> 伤害。',
          steps: [{ kind: 'damage', mul: '%mul', hits: 3, target: 'random' }]
        }
      ]
    },
    {
      id: 'rat_cable', name: '电缆鼠·电击手', role: '控制', color: '#9b8fd0',
      base: { hp: 66, atk: 8, def: 5, spd: 9, crit: 5 },
      passives: [
        {
          id: 'p1', name: '静电', unlock: 1,
          vals: { chance: { b: 20, i: 1, cap: 35 } },
          tmpl: '受到攻击后 {chance}% 几率使攻击者麻痹 1 回合。',
          triggers: [{
            on: 'onTakeDamage', chanceVal: { b: 20, i: 1, cap: 35 },
            effect: { kind: 'status', status: 'stun', turns: 1, target: 'attacker' }
          }]
        },
        {
          id: 'p2', name: '绝缘层', unlock: 10,
          vals: { res: { b: 7, i: 1, cap: 16 } },
          tmpl: '受到伤害降低 <b>{res}%</b>。',
          stat: { dmgTaken: '%res' }
        }
      ],
      ults: [
        {
          id: 'u1', name: '高压电击', cost: 50, unlock: 5, ai: { prio: 3 },
          vals: { mul: { b: 130, i: 2, cap: 168 }, chance: { b: 35, i: 1, cap: 54 }, turns: 2 },
          tmpl: '对单体造成 <b>{mul}%</b> 伤害，{chance}% 几率麻痹 {turns} 回合。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'one' },
            { kind: 'status', status: 'stun', turns: '%turns', chance: '%chance', target: 'one' }
          ]
        },
        {
          id: 'u2', name: '电网', cost: 80, unlock: 15, ai: { prio: 4 },
          vals: { mul: { b: 80, i: 3, cap: 137 }, chance: { b: 30, i: 1, cap: 49 }, turns: 1 },
          tmpl: '对全体造成 <b>{mul}%</b> 伤害，{chance}% 几率麻痹 {turns} 回合。',
          steps: [
            { kind: 'damage', mul: '%mul', target: 'all' },
            { kind: 'status', status: 'stun', turns: '%turns', chance: '%chance', target: 'all' }
          ]
        }
      ]
    }
  ];

  /* --------------------------- 敌方编队 / 地图表 --------------------------- */
  M3.mapTable = [
    { id: 1, name: '猫港（我方领土）', level: 1, enemies: 0, fortress: null },
    { id: 2, name: '锈齿浅滩', level: 3, enemies: 3, fortress: '锈齿哨站' },
    { id: 3, name: '煤烟海峡', level: 5, enemies: 3, fortress: '煤烟熔炉' },
    { id: 4, name: '油污湾', level: 7, enemies: 4, fortress: '油污提炼厂' },
    { id: 5, name: '废铁环礁', level: 9, enemies: 4, fortress: '废铁船坞' },
    { id: 6, name: '毒雾沼泽海', level: 11, enemies: 4, fortress: '毒雾化工塔' },
    { id: 7, name: '齿轮暗流', level: 13, enemies: 4, fortress: '齿轮总装线' },
    { id: 8, name: '蒸汽风暴角', level: 15, enemies: 5, fortress: '蒸汽核心' },
    { id: 9, name: '灰烬深海', level: 17, enemies: 5, fortress: '灰烬中枢' },
    { id: 10, name: '鼠王钢堡', level: 20, enemies: 5, fortress: '联合体总部' }
  ];

  /* ------------------------------ 展示辅助 ------------------------------ */
  /* 解析技能描述里的 {token}（token 指向 vals 的键，或 vals 内的字面值） */
  M3.descOf = function (skill, lv) {
    if (!skill) return '';
    var vals = skill.vals || {};
    return String(skill.tmpl || '').replace(/\{(\w+)\}/g, function (_, key) {
      if (!(key in vals)) return '{' + key + '}';
      var v = vals[key];
      return typeof v === 'object' ? M3.resolve(v, lv) : v;
    });
  };
  /* 技能数值列表（用于展示"每级成长"） */
  M3.skillRows = function (skill) {
    var vals = skill.vals || {};
    return Object.keys(vals).map(function (key) {
      var v = vals[key];
      if (typeof v !== 'object' || v.b === undefined) {
        return { key: key, from: v, to: v, perLevel: 0, cap: null, flat: true };
      }
      return {
        key: key, from: M3.resolve(v, 1), to: M3.resolve(v, 20),
        perLevel: v.i || 0, cap: v.cap === undefined ? null : v.cap, flat: (v.i || 0) === 0
      };
    });
  };
  /* 全部技能槽（含解锁等级），按解锁顺序 */
  M3.slotsOf = function (def) {
    var out = [];
    (def.passives || []).forEach(function (p, i) {
      out.push({ key: 'p' + (i + 1), kind: 'passive', skill: p, unlock: p.unlock || 1 });
    });
    (def.ults || []).forEach(function (u, i) {
      out.push({ key: 'u' + (i + 1), kind: 'ult', skill: u, unlock: u.unlock || 1 });
    });
    return out.sort(function (a, b) { return a.unlock - b.unlock; });
  };

  M3.cats = CATS;
  M3.mice = MICE;
  M3.byId = function (id) {
    var all = CATS.concat(MICE);
    for (var i = 0; i < all.length; i++) if (all[i].id === id) return all[i];
    return null;
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = M3;
})(typeof window !== 'undefined' ? window : globalThis);
