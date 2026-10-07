/* ==========================================================================
 * map3 · 角色图鉴（展示页逻辑）
 * --------------------------------------------------------------------------
 * 展示 10 名我方猫猫 + 10 名老鼠杂兵：
 *   · 属性成长表（1~20 级，全部整数，逐级四舍五入）
 *   · 4 个技能槽的详细效果（被动1/大招1/被动2/大招2），按当前等级解析实时数值
 *   · 技能成长：解锁等级、每级增量、上限、L1→L20 数值区间
 * ========================================================================== */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  };
  /* 只允许 <b> 高亮标签通过 */
  function rich(html) {
    return String(html).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/&lt;b&gt;/g, '<b>').replace(/&lt;\/b&gt;/g, '</b>');
  }

  var state = { side: 'cat', id: 'cat_tuffy', lv: 10 };
  var pool = function () { return state.side === 'cat' ? M3.cats : M3.mice; };
  var current = function () { return M3.byId(state.id) || pool()[0]; };

  /* ------------------------------ 列表 ------------------------------ */
  function roster() {
    var items = pool();
    var html = items.map(function (d) {
      var on = d.id === state.id ? ' on' : '';
      var s = M3.statAt(d.base, state.lv);
      return '<button class="item' + on + '" data-id="' + d.id + '" style="--c:' + d.color + '">' +
        '<span class="glyph">' + esc((d.title || d.name).slice(0, 1)) + '</span>' +
        '<span class="meta"><b>' + esc(d.title || d.name) + '</b><i>' + esc(d.role) + '</i></span>' +
        '<span class="mini">HP ' + s.hp + ' · ATK ' + s.atk + '</span>' +
        '</button>';
    }).join('');
    $('roster').innerHTML = html;
    Array.prototype.forEach.call($('roster').querySelectorAll('.item'), function (btn) {
      btn.onclick = function () { state.id = btn.dataset.id; render(); };
    });
  }

  /* ------------------------------ 属性区 ------------------------------ */
  function statBlock(d) {
    var s = M3.statAt(d.base, state.lv);
    var s1 = M3.statAt(d.base, 1), s20 = M3.statAt(d.base, 20);
    var cells = [
      ['HP', s.hp, s1.hp, s20.hp],
      ['ATK', s.atk, s1.atk, s20.atk],
      ['DEF', s.def, s1.def, s20.def],
      ['SPD', s.spd, s1.spd, s20.spd],
      ['暴击', s.crit + '%', s1.crit + '%', s20.crit + '%']
    ].map(function (c) {
      return '<div class="stat">' +
        '<span class="k">' + c[0] + '</span>' +
        '<span class="v">' + c[1] + '</span>' +
        '<span class="r">Lv1 ' + c[2] + ' → Lv20 ' + c[3] + '</span>' +
        '</div>';
    }).join('');
    return '<div class="stats">' + cells + '</div>';
  }

  /* 1~20 级属性表（整数，逐级四舍五入） */
  function growthTable(d) {
    var rows = M3.statTable(d);
    var head = '<tr><th>等级</th><th>HP</th><th>ATK</th><th>DEF</th><th>SPD</th><th>暴击</th></tr>';
    var body = rows.map(function (r) {
      var on = r.lv === state.lv ? ' class="on"' : '';
      return '<tr' + on + '><td>' + r.lv + '</td><td>' + r.hp + '</td><td>' + r.atk + '</td><td>' +
        r.def + '</td><td>' + r.spd + '</td><td>' + r.crit + '%</td></tr>';
    }).join('');
    return '<div class="tablewrap"><table class="grid"><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div>';
  }

  /* ------------------------------ 技能区 ------------------------------ */
  function skillCard(slot, d) {
    var sk = slot.skill;
    var locked = state.lv < slot.unlock;
    var kindLabel = slot.kind === 'ult' ? '必杀' : '被动';
    var cost = sk.cost ? (sk.cost + ' EN') : '常驻';
    var rows = M3.skillRows(sk);
    var growth = rows.map(function (r) {
      if (!r.perLevel) return '<span class="g"><i>' + esc(r.key) + '</i>固定值 ' + r.from + '</span>';
      var capTxt = r.cap !== null ? '，上限 ' + r.cap : '';
      var now = M3.resolve(sk.vals[r.key], state.lv);
      return '<span class="g"><i>' + esc(r.key) + '</i>本级 Lv' + state.lv + ' <b>' + now +
        '</b> → Lv20 ' + r.to + '　<span class="per">每级 +' + r.perLevel + capTxt + '</span></span>';
    }).join('');
    return '<div class="skill' + (locked ? ' locked' : '') + ' ' + slot.kind + '">' +
      '<div class="shead">' +
      '<span class="tag">' + kindLabel + '</span>' +
      '<b>' + esc(sk.name) + '</b>' +
      '<span class="lvtag">' + (locked ? 'Lv' + slot.unlock + ' 解锁' : '已解锁') + '</span>' +
      '<span class="cost">' + cost + '</span>' +
      '</div>' +
      '<p class="desc">' + rich(M3.descOf(sk, state.lv)) + '</p>' +
      '<div class="growth">' + growth + '</div>' +
      (locked ? '<div class="lockmask">当前等级未解锁（' + state.lv + ' / ' + slot.unlock + '）</div>' : '') +
      '</div>';
  }

  /* ------------------------------ 渲染 ------------------------------ */
  function render() {
    var d = current();
    roster();

    $('dName').textContent = d.title || d.name;
    $('dRole').textContent = d.role + ' · ' + (state.side === 'cat' ? '我方猫猫' : '敌方老鼠');
    $('dGlyph').textContent = (d.title || d.name).slice(0, 1);
    $('dCard').style.setProperty('--c', d.color);
    $('dLv').textContent = state.lv;
    $('dStats').innerHTML = statBlock(d);
    $('dGrowth').innerHTML = growthTable(d);
    $('dSkills').innerHTML = M3.slotsOf(d).map(function (s) { return skillCard(s, d); }).join('');
    $('dNote').textContent = state.side === 'cat'
      ? '我方编队最多 4 人；同级战斗为敌方杂兵强度基准。'
      : '敌方老鼠遵循同一系统（2 被动 + 2 大招），数值上限更保守。';
  }

  document.addEventListener('DOMContentLoaded', function () {
    /* 侧边切换 */
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (t) {
      t.onclick = function () {
        state.side = t.dataset.side;
        state.id = pool()[0].id;
        Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (x) { x.classList.remove('on'); });
        t.classList.add('on');
        render();
      };
    });
    /* 等级控制 */
    $('lv').oninput = function () { state.lv = +this.value; $('dLv').textContent = state.lv; render(); };
    Array.prototype.forEach.call(document.querySelectorAll('.jump'), function (b) {
      b.onclick = function () {
        state.lv = +b.dataset.lv;
        $('lv').value = state.lv;
        render();
      };
    });
    render();
  });

  window.M3Gallery = { render: render, state: state };
})();
