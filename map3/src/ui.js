/* ==========================================================================
 * map3 · 猫鼠远洋 —— 战斗模拟器 UI
 * --------------------------------------------------------------------------
 * 只依赖 M3（data.js + engine.js）。全程自动战斗：点击「出击」后逐条回放战报。
 * 像素风 UI，不含角色立绘（按需求不含角色图像）。
 * ========================================================================== */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); };

  /* 技能槽与解锁等级统一由 data.js 提供（L1/L5/L10/L15），数值随等级解析 */
  function skillSlots(def) { return M3.slotsOf(def); }

  /* -------------------------------- 状态 -------------------------------- */
  var state = {
    catLv: 10, ratLv: 10, ratN: 4,
    catTeam: [],
    ratTeam: [],
    playing: false, timer: null, speed: 1, evIndex: 0, events: null, result: null,
    live: {}
  };

  /* ------------------------------ 编队卡片 ------------------------------ */
  function catCard(def, lv, compact) {
    var st = M3.statAt(def.base, lv);
    var slots = skillSlots(def).map(function (sl) {
      var locked = lv < sl.unlock;
      var desc = M3.descOf(sl.skill, lv).replace(/<[^>]+>/g, '');
      return '<li class="slot ' + sl.kind + (locked ? ' locked' : '') + '" title="' + esc(desc) + '">' +
        '<span class="k">' + (sl.kind === 'ult' ? '必杀' : '被动') + '</span>' +
        '<span class="n">' + esc(sl.skill.name) + '</span>' +
        '<span class="lv">' + (locked ? '🔒 Lv' + sl.unlock : (sl.skill.cost ? sl.skill.cost + 'EN' : '常驻')) + '</span>' +
        '</li>';
    }).join('');
    return '<div class="card" style="--c:' + def.color + '" data-id="' + def.id + '">' +
      '<div class="chead"><span class="glyph">' + esc(def.title.slice(0, 1)) + '</span>' +
      '<div><b>' + esc(def.title) + '</b><i>' + esc(def.role) + ' · Lv' + lv + '</i></div></div>' +
      '<div class="stats">' +
      sbox('HP', st.hp) + sbox('ATK', st.atk) + sbox('DEF', st.def) + sbox('SPD', st.spd) + sbox('CRIT', st.crit + '%') +
      '</div>' +
      (compact ? '' : '<ul class="slots">' + slots + '</ul>') +
      '</div>';
  }
  function sbox(k, v) { return '<span class="sb"><i>' + k + '</i><b>' + v + '</b></span>'; }

  function ratCard(def, lv, compact) {
    var st = M3.statAt(def.base, lv);
    var slots = skillSlots(def).map(function (sl) {
      var locked = lv < sl.unlock;
      var desc = M3.descOf(sl.skill, lv).replace(/<[^>]+>/g, '');
      return '<li class="slot ' + sl.kind + (locked ? ' locked' : '') + '" title="' + esc(desc) + '"><span class="k">' +
        (sl.kind === 'ult' ? '必杀' : '被动') + '</span><span class="n">' + esc(sl.skill.name) + '</span>' +
        '<span class="lv">' + (locked ? '🔒 Lv' + sl.unlock : (sl.skill.cost ? sl.skill.cost + 'EN' : '常驻')) + '</span></li>';
    }).join('');
    return '<div class="card rat" style="--c:' + def.color + '" data-id="' + def.id + '">' +
      '<div class="chead"><span class="glyph">' + esc(def.name.slice(0, 1)) + '</span>' +
      '<div><b>' + esc(def.name) + '</b><i>' + esc(def.role) + ' · Lv' + lv + '</i></div></div>' +
      '<div class="stats">' + sbox('HP', st.hp) + sbox('ATK', st.atk) + sbox('DEF', st.def) + sbox('SPD', st.spd) + '</div>' +
      (compact ? '' : '<ul class="slots">' + slots + '</ul>') +
      '</div>';
  }

  function renderSetup() {
    $('catTeam').innerHTML = state.catTeam.map(function (d) { return catCard(d, state.catLv, false); }).join('');
    $('ratTeam').innerHTML = state.ratTeam.map(function (t) { return ratCard(t.def, t.level, false); }).join('');
  }

  /* ------------------------------- 战场构建 ------------------------------- */
  function buildArena() {
    state.catTeam.forEach(function (d) { M3.makeUnit(d, state.catLv, 'cat'); }); /* 预热 */
    state.ratTeam = state.ratTeam.map(function (t) { return { def: t.def, level: t.level }; });
    var cats = state.catTeam.map(function (d) { return M3.makeUnit(d, state.catLv, 'cat'); });
    var rats = state.ratTeam.map(function (t) { return M3.makeUnit(t.def, t.level, 'rat'); });
    state.units = cats.concat(rats);
    state.live = {};
    state.units.forEach(function (u) { state.live[u.uid] = u; });

    $('sideCats').innerHTML = cats.map(unitRow).join('');
    $('sideRats').innerHTML = rats.map(unitRow).join('');
    $('log').innerHTML = '';
    $('result').textContent = '';
    $('clock').textContent = '预备';
    return { cats: cats, rats: rats };
  }

  function unitRow(u) {
    return '<div class="unit" id="u_' + u.uid.replace(':', '_') + '" style="--c:' + u.color + '">' +
      '<div class="uhead"><span class="glyph">' + esc((u.title || u.name).slice(0, 1)) + '</span>' +
      '<b>' + esc(u.title || u.name) + '</b><i>Lv' + u.level + '</i></div>' +
      '<div class="hpbar"><div class="hpfill" style="width:100%"></div><span class="hptxt">' + u.maxHp + '/' + u.maxHp + '</span></div>' +
      '<div class="enbar"><i></i></div>' +
      '<div class="chips"></div>' +
      '<div class="pop"></div></div>';
  }
  function el(uid) { return $('u_' + uid.replace(':', '_')); }

  function syncUnit(u) {
    var e = el(u.uid); if (!e) return;
    var pct = Math.max(0, u.hp / u.maxHp * 100);
    e.querySelector('.hpfill').style.width = pct.toFixed(1) + '%';
    e.querySelector('.hpfill').classList.toggle('low', pct < 35);
    e.querySelector('.hptxt').textContent = Math.max(0, Math.round(u.hp)) + '/' + u.maxHp;
    e.querySelector('.enbar i').style.width = (u.en / u.enMax * 100) + '%';
    e.classList.toggle('dead', u.dead);
    e.querySelector('.chips').innerHTML = u.statuses.filter(function (s) { return s.turns !== 99 || s.id === 'shield'; })
      .map(function (s) {
        var lbl = M3.STATUS_LABEL[s.id] || s.id;
        var extra = s.id === 'shield' ? Math.round(s.absorb) : (s.value ? Math.round((s.dot ? s.value : s.value * 100) * 10) / 10 : '');
        return '<span class="chip" title="' + esc(lbl) + '">' + esc(lbl) + (extra !== '' && extra !== 0 ? esc(' ' + extra) : '') + '</span>';
      }).join('');
  }

  function pop(uid, text, cls) {
    var e = el(uid); if (!e) return;
    var d = document.createElement('span');
    d.className = 'popup ' + (cls || '');
    d.textContent = text;
    d.style.left = (30 + Math.random() * 40) + '%';
    e.querySelector('.pop').appendChild(d);
    setTimeout(function () { d.remove(); }, 900);
  }

  function log(text, cls) {
    var box = $('log');
    var d = document.createElement('div');
    d.className = 'line ' + (cls || '');
    d.innerHTML = text;
    box.appendChild(d);
    while (box.children.length > 260) box.removeChild(box.firstChild);
    box.scrollTop = box.scrollHeight;
  }

  function nameOf(uid) {
    var u = state.live[uid];
    return u ? '<b style="color:' + u.color + '">' + esc(u.title || u.name) + '</b>' : uid;
  }

  /* ------------------------------- 事件回放 ------------------------------- */
  function playEvents(events, speed) {
    state.events = events;
    state.evIndex = 0;
    state.playing = true;
    tick(speed);
  }
  function tick(speed) {
    clearTimeout(state.timer);
    var step = Math.max(1, Math.round(speed));
    var i = 0;
    while (i < step && state.evIndex < state.events.length) { step1(state.events[state.evIndex++]); i++; }
    if (state.evIndex < state.events.length) {
      state.timer = setTimeout(function () { tick(speed); }, speed < 1 ? 90 / speed : 40);
    } else {
      state.playing = false;
      var r = state.result;
      if (r) log(r.win ? '<span class="win">★ 我方胜利</span>　剩余 ' + r.catsAlive + ' 猫 / ' + r.ratsAlive + ' 鼠' :
        '<span class="lose">✖ 我方失败</span>　剩余 ' + r.catsAlive + ' 猫 / ' + r.ratsAlive + ' 鼠', 'end');
      $('result').innerHTML = r && r.win ? '<span class="win">胜利</span>' : '<span class="lose">失败</span>';
    }
  }
  function fastForward() {
    clearTimeout(state.timer);
    while (state.evIndex < state.events.length) step1(state.events[state.evIndex++]);
    state.playing = false;
    tick(1);
  }

  function step1(e) {
    var u;
    switch (e.t) {
      case 'start': log('⚓ 战斗开始：海面起雾，双方进入交战距离', 'sys'); break;
      case 'turn':
        u = state.live[e.uid];
        var all = document.querySelectorAll('.unit'); for (var i = 0; i < all.length; i++) all[i].classList.remove('acting');
        if (el(e.uid)) el(e.uid).classList.add('acting');
        /* 状态计时 */
        (u ? u.statuses : []).forEach(function (s) { if (s.turns !== 99) s.turns--; });
        (u ? u.statuses : []).forEach(function (s, i2) { if (s.turns <= 0) u.statuses.splice(i2, 1); });
        if (u) syncUnit(u);
        break;
      case 'skill':
        log(nameOf(e.uid) + ' → <span class="sk">【' + esc(e.name) + '】</span>' + (e.cost ? '<span class="cost"> -' + e.cost + 'EN</span>' : ''));
        u = state.live[e.uid]; if (u) { u.en = Math.max(0, u.en - e.cost); if (!e.cost) u.en = Math.min(u.enMax, u.en + 20); syncUnit(u); }
        break;
      case 'damage':
        u = state.live[e.tid];
        if (u) { u.hp = e.targetHp !== undefined ? e.targetHp : Math.max(0, u.hp - e.value); syncUnit(u); }
        pop(e.tid, '-' + e.value, e.crit ? 'crit' : 'dmg');
        if (e.crit) { if (el(e.tid)) { el(e.tid).classList.add('shake'); setTimeout(function () { el(e.tid).classList.remove('shake'); }, 260); } log('　└ <span class="crit">暴击！</span>' + nameOf(e.tid) + ' 受到 ' + e.value + ' 伤害'); }
        break;
      case 'miss': log('　└ 被闪避了'); break;
      case 'absorb': log('　└ 护盾吸收 ' + e.value); break;
      case 'heal':
        u = state.live[e.tid]; if (u) { u.hp = Math.min(u.maxHp, u.hp + e.value); syncUnit(u); }
        pop(e.tid, '+' + e.value, 'heal');
        log('　└ ' + nameOf(e.tid) + ' 回复 ' + e.value + '（' + esc(e.label || '治疗') + '）');
        break;
      case 'status':
        u = state.live[e.tid];
        if (u) {
          u.statuses = u.statuses.filter(function (s) { return !(s.id === e.status && s.turns !== 99); });
          u.statuses.push({ id: e.status, value: e.value, turns: e.turns, absorb: e.absorb, dot: (e.status === 'burn' || e.status === 'poison') ? e.status : null });
          syncUnit(u);
        }
        log('　└ ' + nameOf(e.tid) + ' 获得 <span class="st">' + esc(e.label) + '</span>' + (e.absorb ? '（' + Math.round(e.absorb) + '）' : '') + (e.turns && e.turns !== 99 ? ' ×' + e.turns + '回合' : ''));
        break;
      case 'dot':
        u = state.live[e.tid]; if (u) { u.hp = Math.max(0, u.hp - e.value); syncUnit(u); }
        pop(e.tid, '-' + e.value, 'dot');
        log('　└ ' + nameOf(e.tid) + ' 受到 ' + esc(e.label) + ' ' + e.value + ' 伤害');
        break;
      case 'detonate':
        u = state.live[e.tid]; if (u) { u.hp = Math.max(0, u.hp - e.value); syncUnit(u); }
        pop(e.tid, '-' + e.value, 'dot');
        log('　└ <span class="crit">引爆！</span>' + nameOf(e.tid) + ' 受到 ' + e.value + ' 伤害');
        break;
      case 'death':
        u = state.live[e.uid]; if (u) { u.dead = true; u.hp = 0; syncUnit(u); }
        log('　✝ ' + nameOf(e.uid) + ' 被击沉', 'death');
        break;
      case 'special': log('　└ ' + nameOf(e.uid) + ' 触发【' + esc(e.label) + '】'); break;
      case 'counter': log('　└ ' + nameOf(e.uid) + ' 反击！'); break;
      case 'skip': log('　└ ' + nameOf(e.uid) + ' 无法行动（' + esc(e.label) + '）'); break;
      case 'energy': log('　└ 能量 +' + e.value); break;
      case 'haste': log('　└ ' + nameOf(e.tid) + ' 获得额外行动！'); break;
      case 'selfcost': log('　└ ' + nameOf(e.uid) + ' 承受反冲 ' + e.value); break;
      case 'cleanse': log('　└ 净化了 ' + e.value + ' 个负面状态'); break;
      case 'resist': log('　└ ' + nameOf(e.tid) + ' 抵抗了 ' + esc(e.label)); break;
      case 'end':
        $('clock').textContent = '刻度 ' + e.ticks;
        break;
    }
  }

  /* -------------------------------- 出击 -------------------------------- */
  function fight(instant) {
    if (state.playing) return;
    var built = buildArena();
    var seed = (Math.random() * 1e9) | 0;
    var res = M3.simulate(built.cats, built.rats, seed, true);
    state.result = res;
    log('⚔ <b>我方 ' + state.catTeam.length + ' 舰 vs 鼠群 ' + state.ratTeam.length + ' 舰</b>　（我方 Lv' + state.catLv + ' / 敌方 Lv' + state.ratLv + '，种子 ' + seed + '）', 'sys');
    if (instant) { playEvents(res.events, 1); fastForward(); }
    else playEvents(res.events, state.speed);
  }

  /* ------------------------------ 批量模拟 ------------------------------ */
  function batch(n) {
    n = n || 200;
    var win = 0, ticks = 0, alive = 0, hp = 0, t0 = performance.now();
    for (var i = 0; i < n; i++) {
      var cats = state.catTeam.map(function (d) { return M3.makeUnit(d, state.catLv, 'cat'); });
      var rats = state.ratTeam.map(function (t) { return M3.makeUnit(t.def, t.level, 'rat'); });
      var r = M3.simulate(cats, rats, (Math.random() * 1e9) | 0, false);
      if (r.win) win++;
      ticks += r.ticks; alive += r.catsAlive; hp += r.catHpPct;
    }
    var ms = performance.now() - t0;
    log('📊 <b>批量模拟 ' + n + ' 场</b>：胜率 <span class="win">' + (win / n * 100).toFixed(1) + '%</span>' +
      '　平均 ' + (ticks / n).toFixed(0) + ' 刻度' +
      '　平均存活 ' + (alive / n).toFixed(2) + '/4　平均剩余血量 ' + (hp / n * 100).toFixed(1) + '%' +
      '　（' + ms.toFixed(0) + 'ms）', 'sys');
  }

  /* ------------------------------ 预计胜率 ------------------------------ */
  var fcTimer = null;
  function forecast() {
    clearTimeout(fcTimer);
    fcTimer = setTimeout(function () {
      var n = 40, win = 0;
      for (var i = 0; i < n; i++) {
        var cats = state.catTeam.map(function (d) { return M3.makeUnit(d, state.catLv, 'cat'); });
        var rats = state.ratTeam.map(function (t) { return M3.makeUnit(t.def, t.level, 'rat'); });
        if (M3.simulate(cats, rats, (Math.random() * 1e9) | 0, false).win) win++;
      }
      var p = win / n * 100;
      $('forecast').innerHTML = '预计胜率 <b class="' + (p >= 95 ? 'good' : p >= 60 ? 'mid' : 'bad') + '">' + p.toFixed(0) + '%</b>' +
        '<i>（按当前编队实时采样 40 场）</i>';
    }, 120);
  }

  /* -------------------------------- 交互 -------------------------------- */
  function newCatTeam() { state.catTeam = M3.pickBalancedTeam(M3.cats, 4, Math.random, { level: state.catLv }); }
  function newRatTeam() { state.ratTeam = M3.rollEnemyTeam(state.ratLv, state.ratN, Math.random); }

  function refresh() {
    renderSetup();
    $('catLvV').textContent = state.catLv;
    $('ratLvV').textContent = state.ratLv;
    $('ratNV').textContent = state.ratN;
    $('forecast').innerHTML = '预计胜率 <i>采样中…</i>';
    $('log').innerHTML = '';
    $('result').textContent = '';
    forecast();
  }

  document.addEventListener('DOMContentLoaded', function () {
    newCatTeam(); newRatTeam();
    refresh();

    $('btnRoll').onclick = function () { if (state.playing) return; newCatTeam(); refresh(); };
    $('btnReroll').onclick = function () { if (state.playing) return; newRatTeam(); renderSetup(); forecast(); };
    $('btnFight').onclick = function () { fight(false); };
    $('btnSkip').onclick = function () { if (state.playing) fastForward(); else fight(true); };
    $('btnBatch').onclick = function () { if (state.playing) return; batch(200); };
    $('btnAuto').onclick = function () { newCatTeam(); newRatTeam(); renderSetup(); fight(false); };

    $('catLv').oninput = function () { state.catLv = +this.value; renderSetup(); $('catLvV').textContent = state.catLv; forecast(); };
    $('ratLv').oninput = function () { state.ratLv = +this.value; state.ratTeam.forEach(function (t) { t.level = state.ratLv; }); renderSetup(); $('ratLvV').textContent = state.ratLv; forecast(); };
    $('ratN').oninput = function () {
      state.ratN = +this.value; $('ratNV').textContent = state.ratN;
      while (state.ratTeam.length > state.ratN) state.ratTeam.pop();
      while (state.ratTeam.length < state.ratN) state.ratTeam.push({ def: M3.mice[Math.floor(Math.random() * M3.mice.length)], level: state.ratLv });
      renderSetup(); forecast();
    };
    [['spd1', 1], ['spd2', 2], ['spd4', 4]].forEach(function (p) {
      $(p[0]).onclick = function () {
        state.speed = p[1];
        document.querySelectorAll('.spd').forEach(function (b) { b.classList.remove('on'); });
        this.classList.add('on');
      };
    });
    $('spd1').classList.add('on');

    document.addEventListener('keydown', function (e) {
      if (e.code === 'Space') { e.preventDefault(); fight(false); }
      if (e.code === 'KeyB') batch(200);
    });
  });

  window.M3UI = { batch: batch, forecast: forecast };
})();
