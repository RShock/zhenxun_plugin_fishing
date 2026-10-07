/* ==========================================================================
 * map3 · 猫鼠远洋 —— 角色与技能数据
 * --------------------------------------------------------------------------
 * 世界：老鼠工业联合体在九片海域建厂排污，猫猫远洋舰队逐个攻克要塞。
 * 本文件只负责「战斗系统」的数据层：10 名我方猫猫 + 10 名敌方老鼠杂兵。
 *
 * 数值哲学（低数值 + 乘法公式，扩展性好）：
 *   伤害 = 攻击 × 技能倍率 × 50/(50+防御) × 易伤/减伤 × 暴击 × 随机浮动
 *   属性成长 = 基础值 × (1 + 成长系数 × (等级-1))，等级上限 20。
 *   敌人（杂兵）使用同一套系统与公式，仅基础值更低、技能倍率更保守。
 * ========================================================================== */
(function (root) {
  var M3 = (root.M3 = root.M3 || {});

  /* ------------------------------ 成长曲线 ------------------------------ */
  var G = {
    hp: 0.105,   // L20 ≈ L1 × 2.995
    atk: 0.090,  // L20 ≈ L1 × 2.710
    def: 0.085,  // L20 ≈ L1 × 2.615
    spd: 0.050,  // L20 ≈ L1 × 1.950
    crit: 0.0025 // 每级 +0.25% 暴击
  };
  M3.growth = G;

  function statAt(base, lv) {
    var k = lv - 1;
    return {
      hp: Math.round(base.hp * (1 + G.hp * k)),
      atk: Math.round(base.atk * (1 + G.atk * k) * 10) / 10,
      def: Math.round(base.def * (1 + G.def * k) * 10) / 10,
      spd: Math.round(base.spd * (1 + G.spd * k) * 10) / 10,
      crit: Math.round((base.crit + G.crit * k) * 1000) / 1000
    };
  }
  M3.statAt = statAt;

  /* ------------------------------ 我方猫猫 ------------------------------ */
  /* 技能槽：被动1 / 被动2 / 大招1(50能量) / 大招2(80能量)
     trigger 钩子：onBattleStart / onTurnStart / onTurnEnd / onAttack /
                   onCrit / onTakeDamage / onAllyDown
     step 类型：damage / heal / shield / status / dot / detonate / cleanse
                / energy / haste                                        */
  var CATS = [
    {
      id: 'cat_tuffy', name: '塔菲', title: '橘座·舰长', role: '守护', color: '#f0a132',
      base: { hp: 82, atk: 8.5, def: 9.5, spd: 8, crit: 0.04 },
      passives: [
        {
          id: 'p1', name: '旗舰护航', desc: '战斗开始时为全体队友提供自身攻击 80% 的护盾（2 回合）。',
          triggers: [{ on: 'onBattleStart', effect: { kind: 'shield', mul: 0.8, target: 'allAllies', turns: 2 } }]
        },
        {
          id: 'p2', name: '铁骨舱壁', desc: '受到伤害降低 12%；自身生命低于 50% 时防御 +25%。',
          stat: { dmgTaken: -0.12 },
          dyn: [{ c: 'selfHpBelow', v: 0.5, mod: { defPct: 0.25 } }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '锚定站位', cost: 50, desc: '对全体敌人造成 0.6 倍伤害并嘲讽 2 回合，自身防御 +30%（2 回合）。',
          ai: { prio: 3 }, steps: [
            { kind: 'damage', mul: 0.6, target: 'all' },
            { kind: 'status', status: 'taunt', turns: 2, target: 'self' },
            { kind: 'status', status: 'defUp', value: 0.3, turns: 2, target: 'self' }
          ]
        },
        {
          id: 'u2', name: '舰长怒吼', cost: 80, desc: '全体队友攻击 +25%（3 回合），并回复自身攻击 50% 的生命。',
          ai: { prio: 3 }, steps: [
            { kind: 'status', status: 'atkUp', value: 0.25, turns: 3, target: 'allAllies' },
            { kind: 'heal', mul: 0.5, target: 'allAllies' }
          ]
        }
      ]
    },
    {
      id: 'cat_mia', name: '米娅', title: '白爪·医官', role: '治疗', color: '#7fc8f8',
      base: { hp: 64, atk: 8, def: 6.5, spd: 10, crit: 0.05 },
      passives: [
        {
          id: 'p1', name: '随行药箱', desc: '每回合结束时治疗生命百分比最低的队友，量为自己攻击的 35%。',
          triggers: [{ on: 'onTurnEnd', effect: { kind: 'heal', mul: 0.35, target: 'lowestAlly' } }]
        },
        {
          id: 'p2', name: '无菌手套', desc: '全体队友受到的治疗效果 +20%。',
          stat: { healUp: 0.2 }
        }
      ],
      ults: [
        {
          id: 'u1', name: '急救喷雾', cost: 50, desc: '治疗生命最低的队友（自身攻击 160%），并清除其 1 个负面状态。',
          ai: { prio: 6, cond: { c: 'allyHpBelow', v: 0.7 } }, steps: [
            { kind: 'heal', mul: 1.6, target: 'lowestAlly' },
            { kind: 'cleanse', count: 1, target: 'lowestAlly' }
          ]
        },
        {
          id: 'u2', name: '净化之泉', cost: 80, desc: '治疗全体队友自身攻击 110% 的生命，并附加 2 回合回春。',
          ai: { prio: 5, cond: { c: 'allyHpBelow', v: 0.6 } }, steps: [
            { kind: 'heal', mul: 1.1, target: 'allAllies' },
            { kind: 'dot', id: 'regen', mul: 0.3, turns: 2, target: 'allAllies' }
          ]
        }
      ]
    },
    {
      id: 'cat_shadow', name: '影爪', title: '黑尾·夜刃', role: '爆发', color: '#8e7cf0',
      base: { hp: 58, atk: 13.5, def: 5, spd: 12, crit: 0.15 },
      passives: [
        {
          id: 'p1', name: '暗夜猎手', desc: '对生命低于 40% 的敌人造成伤害 +35%。',
          triggers: [{
            on: 'onBeforeDamage', cond: { c: 'targetHpBelow', v: 0.4 },
            effect: { kind: 'damageMod', value: 1.35 }
          }]
        },
        {
          id: 'p2', name: '致命一击', desc: '暴击率 +10%，暴击伤害 +30%。',
          stat: { critAdd: 0.1, critDmgAdd: 0.3 }
        }
      ],
      ults: [
        {
          id: 'u1', name: '三步连斩', cost: 50, desc: '对单体造成 3 段 0.6 倍伤害，每段独立判定暴击。',
          ai: { prio: 4 }, steps: [{ kind: 'damage', mul: 0.6, hits: 3, target: 'one' }]
        },
        {
          id: 'u2', name: '背刺处决', cost: 80, desc: '对单体造成 2.4 倍伤害；目标生命低于 35% 时伤害 ×1.6。',
          ai: { prio: 5 }, steps: [{
            kind: 'damage', mul: 2.4, target: 'one', execute: { below: 0.35, mul: 1.6 }
          }]
        }
      ]
    },
    {
      id: 'cat_macchiato', name: '玛奇朵', title: '布偶·炮手', role: '群攻', color: '#e88fb0',
      base: { hp: 60, atk: 12.5, def: 5, spd: 9, crit: 0.07 },
      passives: [
        {
          id: 'p1', name: '重装弹链', desc: '每次造成伤害后自身攻击 +6%，最多叠加到 +30%。',
          triggers: [{
            on: 'onAttack',
            effect: { kind: 'status', status: 'atkUp', value: 0.06, turns: 99, target: 'self', stackMax: 5 }
          }]
        },
        {
          id: 'p2', name: '散弹装填', desc: '普攻有 40% 几率改为对全体敌人造成 0.7 倍伤害。',
          triggerSpecial: { kind: 'spread', chance: 0.4, mul: 0.7 }
        }
      ],
      ults: [
        {
          id: 'u1', name: '齐射', cost: 50, desc: '对全体敌人造成 0.85 倍伤害。',
          ai: { prio: 4, cond: { c: 'enemyCountGE', v: 3 } }, steps: [{ kind: 'damage', mul: 0.85, target: 'all' }]
        },
        {
          id: 'u2', name: '饱和轰炸', cost: 80, desc: '对全体敌人造成 1.25 倍伤害，并使其防御 -20%（2 回合）。',
          ai: { prio: 5 }, steps: [
            { kind: 'damage', mul: 1.25, target: 'all' },
            { kind: 'status', status: 'defDown', value: 0.2, turns: 2, target: 'all' }
          ]
        }
      ]
    },
    {
      id: 'cat_abao', name: '阿豹', title: '狸花·督头', role: '指挥', color: '#c9a227',
      base: { hp: 66, atk: 10, def: 7, spd: 11, crit: 0.06 },
      passives: [
        {
          id: 'p1', name: '战吼', desc: '战斗开始时全体队友攻击 +12%。',
          triggers: [{ on: 'onBattleStart', effect: { kind: 'status', status: 'atkUp', value: 0.12, turns: 99, target: 'allAllies' } }]
        },
        {
          id: 'p2', name: '甲板指挥', desc: '每回合开始时为能量最低的队友充能 8 点。',
          triggers: [{ on: 'onTurnStart', effect: { kind: 'energy', amount: 8, target: 'lowestEnergyAlly' } }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '压制射击', cost: 50, desc: '对单体造成 1.1 倍伤害，并使其攻击 -25%（2 回合）。',
          ai: { prio: 3 }, steps: [
            { kind: 'damage', mul: 1.1, target: 'oneHighestAtk' },
            { kind: 'status', status: 'atkDown', value: 0.25, turns: 2, target: 'oneHighestAtk' }
          ]
        },
        {
          id: 'u2', name: '全力突击', cost: 80, desc: '全体队友攻击 +30%、速度 +20%（3 回合）。',
          ai: { prio: 4, cond: { c: 'turnLE', v: 3 } }, steps: [
            { kind: 'status', status: 'atkUp', value: 0.3, turns: 3, target: 'allAllies' },
            { kind: 'status', status: 'spdUp', value: 0.2, turns: 3, target: 'allAllies' }
          ]
        }
      ]
    },
    {
      id: 'cat_denguang', name: '电光', title: '暹罗·斥候', role: '连击', color: '#5fd3c4',
      base: { hp: 56, atk: 11.5, def: 5, spd: 15, crit: 0.1 },
      passives: [
        { id: 'p1', name: '猫步', desc: '闪避 +12%。', stat: { dodge: 0.12 } },
        {
          id: 'p2', name: '连环爪', desc: '普攻后有 45% 几率追加一次 0.5 倍伤害的追击。',
          triggerSpecial: { kind: 'pursuit', chance: 0.45, mul: 0.5 }
        }
      ],
      ults: [
        {
          id: 'u1', name: '疾风突袭', cost: 50, desc: '对单体造成 1.3 倍伤害，并使自身立即获得一次额外行动。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 1.3, target: 'one' },
            { kind: 'haste', target: 'self' }
          ]
        },
        {
          id: 'u2', name: '残影乱舞', cost: 80, desc: '对随机敌人造成 4 段 0.7 倍伤害，并获得 2 回合闪避 +25%。',
          ai: { prio: 5 }, steps: [
            { kind: 'damage', mul: 0.7, hits: 4, target: 'random' },
            { kind: 'status', status: 'dodge', value: 0.25, turns: 2, target: 'self' }
          ]
        }
      ]
    },
    {
      id: 'cat_anchor', name: '大副', title: '缅因·铁锚', role: '破防', color: '#9c8262',
      base: { hp: 74, atk: 12, def: 8.5, spd: 7, crit: 0.08 },
      passives: [
        { id: 'p1', name: '巨力', desc: '攻击 +10%，无视目标 20% 防御。', stat: { atkPct: 0.1, defPen: 0.2 } },
        { id: 'p2', name: '压舱石', desc: '受到伤害降低 8%。', stat: { dmgTaken: -0.08 } }
      ],
      ults: [
        {
          id: 'u1', name: '碎甲重锤', cost: 50, desc: '对单体造成 1.5 倍伤害，并降低其 30% 防御（3 回合）。',
          ai: { prio: 3 }, steps: [
            { kind: 'damage', mul: 1.5, target: 'one' },
            { kind: 'status', status: 'defDown', value: 0.3, turns: 3, target: 'one' }
          ]
        },
        {
          id: 'u2', name: '一击必沉', cost: 80, desc: '对单体造成 2.5 倍伤害，并有 50% 几率晕眩 1 回合。',
          ai: { prio: 5 }, steps: [
            { kind: 'damage', mul: 2.5, target: 'one' },
            { kind: 'status', status: 'stun', turns: 1, chance: 0.5, target: 'one' }
          ]
        }
      ]
    },
    {
      id: 'cat_gear', name: '齿轮', title: '三花·机械师', role: '持续伤害', color: '#f2803c',
      base: { hp: 62, atk: 11, def: 6, spd: 10, crit: 0.06 },
      passives: [
        {
          id: 'p1', name: '蒸汽锅炉', desc: '每次造成伤害后为目标附加 1 层灼烧（自身攻击 18%，2 回合）。',
          triggers: [{ on: 'onAttack', effect: { kind: 'dot', id: 'burn', mul: 0.18, turns: 2, target: 'lastHit' } }]
        },
        {
          id: 'p2', name: '自动扳手', desc: '每回合结束时为随机一名敌人附加 1 层灼烧。',
          triggers: [{ on: 'onTurnEnd', effect: { kind: 'dot', id: 'burn', mul: 0.18, turns: 2, target: 'randomEnemy' } }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '燃油喷射', cost: 50, desc: '对全体敌人造成 0.7 倍伤害，并附加灼烧（自身攻击 30%，2 回合）。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 0.7, target: 'all' },
            { kind: 'dot', id: 'burn', mul: 0.3, turns: 2, target: 'all' }
          ]
        },
        {
          id: 'u2', name: '过载核心', cost: 80, desc: '对单体造成 1.6 倍伤害，并引爆其灼烧（每层额外造成自身攻击 50%，最多 3 层）。',
          ai: { prio: 5, cond: { c: 'enemiesWithDot' } }, steps: [
            { kind: 'damage', mul: 1.6, target: 'one' },
            { kind: 'detonate', dotId: 'burn', mul: 0.5, maxStacks: 3, target: 'one' }
          ]
        }
      ]
    },
    {
      id: 'cat_sherry', name: '雪莉', title: '银渐·炮术长', role: '控制', color: '#a8c6e8',
      base: { hp: 60, atk: 12, def: 5.5, spd: 10, crit: 0.08 },
      passives: [
        {
          id: 'p1', name: '元素充能', desc: '暴击时回复 12 点能量。',
          triggers: [{ on: 'onCrit', effect: { kind: 'energy', amount: 12, target: 'self' } }]
        },
        {
          id: 'p2', name: '霜之护盾', desc: '生命首次低于 60% 时获得自身攻击 70% 的护盾。',
          triggers: [{
            on: 'onTurnStart', once: true, cond: { c: 'selfHpBelow', v: 0.6 },
            effect: { kind: 'shield', mul: 0.7, target: 'self', turns: 99 }
          }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '冰锥散射', cost: 50, desc: '对全体敌人造成 0.75 倍伤害，35% 几率冰冻 1 回合。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 0.75, target: 'all' },
            { kind: 'status', status: 'stun', turns: 1, chance: 0.35, target: 'all' }
          ]
        },
        {
          id: 'u2', name: '暴风雪', cost: 80, desc: '对全体敌人造成 1.15 倍伤害并降低 25% 速度（2 回合），对被冰冻者伤害 +25%。',
          ai: { prio: 5 }, steps: [
            { kind: 'damage', mul: 1.15, target: 'all', bonusVsStunned: 0.25 },
            { kind: 'status', status: 'spdDown', value: 0.25, turns: 2, target: 'all' }
          ]
        }
      ]
    },
    {
      id: 'cat_pudding', name: '布丁', title: '奶牛·水手长', role: '吸血', color: '#6f7bd6',
      base: { hp: 78, atk: 11.5, def: 7.5, spd: 9, crit: 0.09 },
      passives: [
        { id: 'p1', name: '嗜血', desc: '造成伤害的 18% 回复自身生命。', stat: { lifesteal: 0.18 } },
        {
          id: 'p2', name: '背水一战', desc: '每损失 10% 生命，攻击 +6%（最多 +48%）。',
          stat: { rampAtk: [0.6, 0.48] }
        }
      ],
      ults: [
        {
          id: 'u1', name: '利爪连击', cost: 50, desc: '对单体造成 3 段 0.55 倍伤害，每段按伤害的 25% 回复自身。',
          ai: { prio: 4 }, steps: [{ kind: 'damage', mul: 0.55, hits: 3, target: 'one', lifesteal: 0.25 }]
        },
        {
          id: 'u2', name: '狂澜', cost: 80, desc: '对全体敌人造成 1.0 倍伤害，并按总伤害的 30% 回复自身。',
          ai: { prio: 5 }, steps: [{ kind: 'damage', mul: 1.0, target: 'all', lifesteal: 0.3 }]
        }
      ]
    }
  ];

  /* ------------------------------ 敌方老鼠 ------------------------------ */
  /* 杂兵：同一套系统（4 个技能槽），但基础值更低、倍率更保守。 */
  var MICE = [
    {
      id: 'rat_gear', name: '齿轮鼠·工兵', role: '近战', color: '#9aa4b2',
      base: { hp: 60, atk: 8.6, def: 5.4, spd: 9, crit: 0.04 },
      passives: [
        {
          id: 'p1', name: '流水线', desc: '受到伤害后 20% 几率反击 0.5 倍伤害。',
          triggers: [{ on: 'onTakeDamage', chance: 0.2, effect: { kind: 'damage', mul: 0.5, target: 'attacker' } }]
        },
        { id: 'p2', name: '标准件', desc: '攻击 +8%。', stat: { atkPct: 0.08 } }
      ],
      ults: [
        {
          id: 'u1', name: '扳手敲击', cost: 50, desc: '对单体造成 1.3 倍伤害。',
          ai: { prio: 3 }, steps: [{ kind: 'damage', mul: 1.3, target: 'one' }]
        },
        {
          id: 'u2', name: '冲压机', cost: 80, desc: '对单体造成 1.9 倍伤害，自身承受最大生命 6% 的损耗。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 1.9, target: 'one' },
            { kind: 'selfHpCost', v: 0.06, target: 'self' }
          ]
        }
      ]
    },
    {
      id: 'rat_chimney', name: '烟囱鼠·炉工', role: '灼烧', color: '#8a6b5a',
      base: { hp: 56, atk: 9.2, def: 4.4, spd: 8, crit: 0.05 },
      passives: [
        {
          id: 'p1', name: '余烬', desc: '每次造成伤害后附加灼烧（自身攻击 12%，2 回合）。',
          triggers: [{ on: 'onAttack', effect: { kind: 'dot', id: 'burn', mul: 0.12, turns: 2, target: 'lastHit' } }]
        },
        { id: 'p2', name: '耐火砖', desc: '受到伤害降低 8%。', stat: { dmgTaken: -0.08 } }
      ],
      ults: [
        {
          id: 'u1', name: '喷焰', cost: 50, desc: '对全体造成 0.6 倍伤害并附加灼烧（自身攻击 18%，2 回合）。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 0.6, target: 'all' },
            { kind: 'dot', id: 'burn', mul: 0.18, turns: 2, target: 'all' }
          ]
        },
        {
          id: 'u2', name: '煤渣爆燃', cost: 80, desc: '对全体造成 0.8 倍伤害并使其攻击 -15%（2 回合）。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 0.8, target: 'all' },
            { kind: 'status', status: 'atkDown', value: 0.15, turns: 2, target: 'all' }
          ]
        }
      ]
    },
    {
      id: 'rat_oil', name: '油污鼠·技师', role: '减益', color: '#7d8a6a',
      base: { hp: 58, atk: 8.2, def: 5, spd: 9, crit: 0.04 },
      passives: [
        { id: 'p1', name: '油滑', desc: '闪避 +8%。', stat: { dodge: 0.08 } },
        { id: 'p2', name: '润滑', desc: '速度 +10%。', stat: { spdPct: 0.1 } }
      ],
      ults: [
        {
          id: 'u1', name: '泼油', cost: 50, desc: '对单体造成 0.9 倍伤害并降低其攻击 20%（2 回合）。',
          ai: { prio: 3 }, steps: [
            { kind: 'damage', mul: 0.9, target: 'oneHighestAtk' },
            { kind: 'status', status: 'atkDown', value: 0.2, turns: 2, target: 'oneHighestAtk' }
          ]
        },
        {
          id: 'u2', name: '油污爆燃', cost: 80, desc: '对全体造成 0.7 倍伤害并降低速度 20%（2 回合）。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 0.7, target: 'all' },
            { kind: 'status', status: 'spdDown', value: 0.2, turns: 2, target: 'all' }
          ]
        }
      ]
    },
    {
      id: 'rat_shield', name: '铁屑鼠·盾卫', role: '坦克', color: '#8f9aa8',
      base: { hp: 68, atk: 7.2, def: 7.4, spd: 7, crit: 0.03 },
      passives: [
        { id: 'p1', name: '废铁外壳', desc: '受到伤害降低 10%。', stat: { dmgTaken: -0.1 } },
        {
          id: 'p2', name: '拾荒', desc: '每回合开始回复自身攻击 15% 的生命。',
          triggers: [{ on: 'onTurnStart', effect: { kind: 'heal', mul: 0.15, target: 'self' } }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '铁盾冲撞', cost: 50, desc: '对单体造成 0.9 倍伤害，嘲讽 2 回合并使自身防御 +25%（2 回合）。',
          ai: { prio: 2 }, steps: [
            { kind: 'damage', mul: 0.9, target: 'oneHighestAtk' },
            { kind: 'status', status: 'taunt', turns: 2, target: 'self' },
            { kind: 'status', status: 'defUp', value: 0.25, turns: 2, target: 'self' }
          ]
        },
        {
          id: 'u2', name: '磁力壁垒', cost: 80, desc: '为全体队友提供自身攻击 90% 的护盾（2 回合）。',
          ai: { prio: 4 }, steps: [{ kind: 'shield', mul: 0.9, target: 'allAllies', turns: 2 }]
        }
      ]
    },
    {
      id: 'rat_spring', name: '弹簧鼠·突袭兵', role: '连击', color: '#b58fb0',
      base: { hp: 52, atk: 8.8, def: 4, spd: 13, crit: 0.08 },
      passives: [
        {
          id: 'p1', name: '弹簧腿', desc: '普攻有 30% 几率追加 0.5 倍伤害。',
          triggerSpecial: { kind: 'pursuit', chance: 0.30, mul: 0.5 }
        },
        { id: 'p2', name: '弹跳', desc: '闪避 +6%。', stat: { dodge: 0.06 } }
      ],
      ults: [
        {
          id: 'u1', name: '弹射突袭', cost: 50, desc: '对单体造成 2 段 0.65 倍伤害。',
          ai: { prio: 3 }, steps: [{ kind: 'damage', mul: 0.65, hits: 2, target: 'one' }]
        },
        {
          id: 'u2', name: '连环弹射', cost: 80, desc: '对随机敌人造成 3 段 0.75 倍伤害。',
          ai: { prio: 4 }, steps: [{ kind: 'damage', mul: 0.75, hits: 3, target: 'random' }]
        }
      ]
    },
    {
      id: 'rat_sewer', name: '污水鼠·投手', role: '毒伤', color: '#6f9a7a',
      base: { hp: 56, atk: 8.8, def: 4, spd: 8, crit: 0.04 },
      passives: [
        {
          id: 'p1', name: '污染物', desc: '造成伤害后附加中毒（自身攻击 10%，2 回合）。',
          triggers: [{ on: 'onAttack', effect: { kind: 'dot', id: 'poison', mul: 0.1, turns: 2, target: 'lastHit' } }]
        },
        { id: 'p2', name: '防腐皮', desc: '中毒与灼烧伤害降低 30%。', stat: { dotTaken: -0.3 } }
      ],
      ults: [
        {
          id: 'u1', name: '污水弹', cost: 50, desc: '对全体造成 0.55 倍伤害并附加中毒（自身攻击 15%，2 回合）。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 0.55, target: 'all' },
            { kind: 'dot', id: 'poison', mul: 0.15, turns: 2, target: 'all' }
          ]
        },
        {
          id: 'u2', name: '下水道洪流', cost: 80, desc: '对全体造成 0.8 倍伤害并附加中毒（自身攻击 20%，2 回合）。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 0.8, target: 'all' },
            { kind: 'dot', id: 'poison', mul: 0.2, turns: 2, target: 'all' }
          ]
        }
      ]
    },
    {
      id: 'rat_wrench', name: '扳手鼠·修理工', role: '治疗', color: '#c2a06a',
      base: { hp: 58, atk: 7.2, def: 5, spd: 9, crit: 0.03 },
      passives: [
        {
          id: 'p1', name: '备用零件', desc: '每回合结束治疗生命最低的队友（自身攻击 22%）。',
          triggers: [{ on: 'onTurnEnd', effect: { kind: 'heal', mul: 0.22, target: 'lowestAlly' } }]
        },
        { id: 'p2', name: '组装', desc: '全体队友受到的治疗 +10%。', stat: { healUp: 0.1 } }
      ],
      ults: [
        {
          id: 'u1', name: '紧急维修', cost: 50, desc: '治疗生命最低的队友（自身攻击 110%）。',
          ai: { prio: 6, cond: { c: 'allyHpBelow', v: 0.7 } }, steps: [{ kind: 'heal', mul: 1.1, target: 'lowestAlly' }]
        },
        {
          id: 'u2', name: '流水线检修', cost: 80, desc: '治疗全体队友（自身攻击 70%）并清除 1 个负面状态。',
          ai: { prio: 5, cond: { c: 'allyHpBelow', v: 0.65 } }, steps: [
            { kind: 'heal', mul: 0.7, target: 'allAllies' },
            { kind: 'cleanse', count: 1, target: 'allAllies' }
          ]
        }
      ]
    },
    {
      id: 'rat_powder', name: '火药鼠·爆破手', role: '爆发', color: '#d08050',
      base: { hp: 52, atk: 10.2, def: 3.4, spd: 10, crit: 0.1 },
      passives: [
        { id: 'p1', name: '不稳定火药', desc: '自身受到伤害 +5%，暴击率 +8%。', stat: { dmgTaken: 0.05, critAdd: 0.08 } },
        {
          id: 'p2', name: '引信', desc: '攻击生命低于 50% 的目标时伤害 +15%。',
          triggers: [{
            on: 'onBeforeDamage', cond: { c: 'targetHpBelow', v: 0.5 },
            effect: { kind: 'damageMod', value: 1.15 }
          }]
        }
      ],
      ults: [
        {
          id: 'u1', name: '炸药包', cost: 50, desc: '对单体造成 1.7 倍伤害，自身承受最大生命 7% 的损耗。',
          ai: { prio: 3 }, steps: [
            { kind: 'damage', mul: 1.7, target: 'one' },
            { kind: 'selfHpCost', v: 0.07, target: 'self' }
          ]
        },
        {
          id: 'u2', name: '连环爆破', cost: 80, desc: '对全体造成 0.9 倍伤害，自身承受最大生命 10% 的损耗。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 0.9, target: 'all' },
            { kind: 'selfHpCost', v: 0.1, target: 'self' }
          ]
        }
      ]
    },
    {
      id: 'rat_turbo', name: '涡轮鼠·飞轮兵', role: '增速', color: '#7fa8c9',
      base: { hp: 54, atk: 8.2, def: 4.4, spd: 12, crit: 0.06 },
      passives: [
        {
          id: 'p1', name: '涡轮', desc: '每回合开始速度 +3%（可叠加）。',
          triggers: [{
            on: 'onTurnStart',
            effect: { kind: 'status', status: 'spdUp', value: 0.03, turns: 99, target: 'self', stackMax: 8 }
          }]
        },
        { id: 'p2', name: '离心', desc: '受到伤害降低 6%。', stat: { dmgTaken: -0.06 } }
      ],
      ults: [
        {
          id: 'u1', name: '高速切割', cost: 50, desc: '对单体造成 1.1 倍伤害，并使自身速度 +20%（2 回合）。',
          ai: { prio: 3 }, steps: [
            { kind: 'damage', mul: 1.1, target: 'one' },
            { kind: 'status', status: 'spdUp', value: 0.2, turns: 2, target: 'self' }
          ]
        },
        {
          id: 'u2', name: '旋风乱斩', cost: 80, desc: '对随机敌人造成 3 段 0.7 倍伤害。',
          ai: { prio: 4 }, steps: [{ kind: 'damage', mul: 0.7, hits: 3, target: 'random' }]
        }
      ]
    },
    {
      id: 'rat_cable', name: '电缆鼠·电击手', role: '控制', color: '#9b8fd0',
      base: { hp: 55, atk: 8.8, def: 4.4, spd: 10, crit: 0.05 },
      passives: [
        {
          id: 'p1', name: '静电', desc: '受到攻击后 20% 几率使攻击者麻痹 1 回合。',
          triggers: [{ on: 'onTakeDamage', chance: 0.2, effect: { kind: 'status', status: 'stun', turns: 1, target: 'attacker' } }]
        },
        { id: 'p2', name: '绝缘层', desc: '受到伤害降低 7%。', stat: { dmgTaken: -0.07 } }
      ],
      ults: [
        {
          id: 'u1', name: '高压电击', cost: 50, desc: '对单体造成 1.3 倍伤害，35% 几率麻痹 2 回合。',
          ai: { prio: 3 }, steps: [
            { kind: 'damage', mul: 1.3, target: 'one' },
            { kind: 'status', status: 'stun', turns: 2, chance: 0.35, target: 'one' }
          ]
        },
        {
          id: 'u2', name: '电网', cost: 80, desc: '对全体造成 0.8 倍伤害，30% 几率麻痹 1 回合。',
          ai: { prio: 4 }, steps: [
            { kind: 'damage', mul: 0.8, target: 'all' },
            { kind: 'status', status: 'stun', turns: 1, chance: 0.3, target: 'all' }
          ]
        }
      ]
    }
  ];

  /* --------------------------- 敌方编队 / 难度 --------------------------- */
  /* 后续航海玩法用：地图难度 -> 建议等级与敌人数（本期只用于模拟器取参） */
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

  M3.cats = CATS;
  M3.mice = MICE;
  M3.byId = function (id) {
    var all = CATS.concat(MICE);
    for (var i = 0; i < all.length; i++) if (all[i].id === id) return all[i];
    return null;
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = M3;
})(typeof window !== 'undefined' ? window : globalThis);
