// S2 星穹矿脉 · 黑盒试玩驱动器
// 用途：以玩家视角黑盒试玩 web/static/s2-vnext（jsdom 加载真实页面 + dialog polyfill），
//      通过 HTTP API 查询 UI / 点击按钮 / 推进时间，不修改游戏逻辑。
// 启动：node tools/s2_playtest_driver.mjs [bundle目录] [端口]
//   bundle 目录需包含 esbuild 打包产物 bundle.js（iife 格式，入口 app.js），
//   以及 game_data.json；打包方式见本文件底部注释。
import { JSDOM, VirtualConsole } from 'jsdom';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, '..');
const SRC = path.join(REPO, 'web/static/s2-vnext');
const BUNDLE_DIR = process.argv[2] ? path.resolve(process.argv[2]) : __dirname;
const PORT = Number(process.argv[3] || 8222);
const STATE_FILE = path.join(BUNDLE_DIR, 'state.json');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml' };

let dom = null, errors = [], logs = [];

function loadPatchedHtml() {
  // 仅替换模块加载方式（esbuild iife 产物），游戏代码本身不改动
  let html = fs.readFileSync(path.join(SRC, 'index.html'), 'utf-8');
  html = html.replace(/<script type="module"[^>]*><\/script>/, '<script src="/__bundle.js"></script>');
  return html;
}

function bootJsdom() {
  errors = []; logs = [];
  const vc = new VirtualConsole();
  vc.on('error', (...a) => errors.push(a.map(String).join(' ')));
  vc.on('warn', (...a) => logs.push('[warn] ' + a.map(String).join(' ')));
  vc.on('log', (...a) => { if (logs.length < 200) logs.push(a.map(String).join(' ')); });
  vc.on('jsdomError', (e) => errors.push('jsdomError: ' + e.message));

  const dom = new JSDOM(loadPatchedHtml(), {
    url: `http://127.0.0.1:${PORT}/__play.html`,
    runScripts: 'dangerously',
    resources: 'usable',
    pretendToBeVisual: true,
    virtualConsole: vc,
    beforeParse(window) {
      try {
        if (fs.existsSync(STATE_FILE)) {
          const saved = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
          for (const [k, v] of Object.entries(saved)) window.localStorage.setItem(k, v);
        }
      } catch (e) { errors.push('restore failed: ' + e.message); }
      window.fetch = (input, init) => {
        const u = new URL(typeof input === 'string' ? input : input.url, window.location.href);
        return globalThis.fetch(u, init);
      };
      // jsdom 缺失 API 的 polyfill（仅补平台差异，不改变游戏逻辑）
      const dlg = window.HTMLDialogElement && window.HTMLDialogElement.prototype;
      if (dlg && !dlg.close) {
        dlg.close = function () { this.removeAttribute('open'); this.dispatchEvent(new window.Event('close')); };
        dlg.show = function () { this.setAttribute('open', ''); };
        dlg.showModal = function () { this.setAttribute('open', ''); };
      }
      const form = window.HTMLFormElement && window.HTMLFormElement.prototype;
      if (form && !form.requestSubmit) {
        form.requestSubmit = function () {
          if ((this.getAttribute('method') || '').toLowerCase() === 'dialog') {
            const d = this.closest('dialog'); if (d && d.close) d.close();
          }
        };
      }
    },
  });
  return dom;
}

function saveState() {
  try {
    const ls = dom?.window?.localStorage;
    if (!ls) return;
    const obj = {};
    for (let i = 0; i < ls.length; i++) { const k = ls.key(i); obj[k] = ls.getItem(k); }
    fs.writeFileSync(STATE_FILE, JSON.stringify(obj, null, 1));
  } catch (e) { errors.push('save failed: ' + e.message); }
}

function visible(el) {
  if (!el || el.nodeType !== 1) return false;
  if (el.hasAttribute?.('hidden')) return false;
  if (el.tagName === 'DIALOG') return el.hasAttribute('open');
  const st = el.getAttribute?.('style') || '';
  if (/display\s*:\s*none/.test(st)) return false;
  return true;
}
function ownText(el) {
  let t = '';
  for (const n of el.childNodes) if (n.nodeType === 3) t += n.textContent;
  return t.replace(/\s+/g, ' ').trim();
}
function dumpTree(el, out, depth, maxDepth) {
  if (depth > maxDepth || out.lines.length > out.limit) return;
  if (!visible(el)) return;
  const tag = el.tagName.toLowerCase();
  if (['script', 'style', 'noscript', 'link', 'meta', 'template'].includes(tag)) return;
  const id = el.id ? `#${el.id}` : '';
  const cls = el.classList?.length ? `.${[...el.classList].slice(0, 3).join('.')}` : '';
  let mark = '';
  if (tag === 'button') mark = '[BTN]';
  else if (tag === 'input') mark = el.type === 'checkbox' ? `[CHK:${el.checked ? 'x' : ' '}]` : `[INPUT:${el.value}]`;
  else if (tag === 'select') mark = `[SEL:${el.value}]`;
  else if (tag === 'option') { if (el.selected) out.lines.push(`${'  '.repeat(depth)}• ${el.textContent.trim()}`); return; }
  const txt = ownText(el);
  if (mark || txt || id) {
    let line = `${'  '.repeat(depth)}${mark ? mark + ' ' : ''}${tag}${id}${cls}`;
    if (txt) line += ` "${txt.slice(0, 160)}"`;
    if (tag === 'button' && el.disabled) line += ' (禁用)';
    out.lines.push(line);
  }
  for (const c of el.children) dumpTree(c, out, depth + 1, maxDepth);
}
function dumpUI(rootSel, maxDepth, limit) {
  const doc = dom.window.document;
  const root = rootSel ? doc.querySelector(rootSel) : doc.body;
  if (!root) return '选择器无匹配';
  const out = { lines: [], limit: limit || 400 };
  dumpTree(root, out, 0, maxDepth || 18);
  return out.lines.join('\n');
}
function stats() {
  const doc = dom.window.document;
  const rows = [];
  const rx = /(Value|Rate|Count|Multiplier|Eta|Progress$|ProgressText|Name$|State|Title|Summary|Announcement|Notice|Reason|Next$|Spent|Result|Countdown|Elapsed|Speed|Threshold|LockedReward|GoalNote|History$|Empty)/;
  doc.querySelectorAll('[id]').forEach(el => {
    if (!rx.test(el.id)) return;
    if (!visible(el)) return;
    const t = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (t) rows.push(`${el.id} = ${t.slice(0, 120)}`);
  });
  return rows.join('\n');
}

function findButton(q) {
  const doc = dom.window.document;
  if (q.id) return doc.getElementById(q.id);
  if (q.text) {
    const t = decodeURIComponent(q.text);
    const cands = [...doc.querySelectorAll('button, [role="tab"], input, select')].filter(visible);
    const matches = cands.filter(b => (b.textContent || b.value || '').replace(/\s+/g, ' ').trim().includes(t));
    const n = parseInt(q.n || '1', 10) - 1;
    return matches[n] || matches[0];
  }
  return null;
}
function result(extra) {
  saveState();
  const notice = dom.window.document.getElementById('actionNotice');
  const o = { ...extra };
  if (notice && visible(notice) && notice.textContent.trim()) o.notice = notice.textContent.trim();
  return JSON.stringify(o, null, 1);
}
const wait = (ms) => new Promise(r => setTimeout(r, ms));

const server = http.createServer((req, res) => {
  const u = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const send = (body, type = 'text/plain; charset=utf-8', code = 200) => { res.writeHead(code, { 'Content-Type': type }); res.end(body); };

  if (u.pathname === '/__play.html') return send(loadPatchedHtml(), 'text/html; charset=utf-8');
  const bundlePath = path.join(BUNDLE_DIR, 'bundle.js');
  if (u.pathname === '/__bundle.js') {
    if (!fs.existsSync(bundlePath)) return send('bundle.js 不存在，请先构建（见文件底部注释）', 'text/plain', 500);
    return send(fs.readFileSync(bundlePath), 'text/javascript');
  }
  const file = path.join(SRC, path.normalize(u.pathname).replace(/^(\.\.[/\\])+/, ''));
  if (file.startsWith(SRC) && fs.existsSync(file) && fs.statSync(file).isFile()) {
    return send(fs.readFileSync(file), MIME[path.extname(file)] || 'application/octet-stream');
  }

  if (!u.pathname.startsWith('/cmd/')) return send('not found', 'text/plain', 404);
  const q = Object.fromEntries(u.searchParams);
  try {
    if (!dom) return send('driver 未就绪', 'text/plain', 503);
    if (u.pathname === '/cmd/ui') return send(dumpUI(q.sel ? decodeURIComponent(q.sel) : null, q.depth ? +q.depth : 18, q.limit ? +q.limit : 400));
    if (u.pathname === '/cmd/stats') return send(stats());
    if (u.pathname === '/cmd/read') {
      const el = dom.window.document.querySelector(decodeURIComponent(q.sel));
      return send(el ? (el.textContent || '').replace(/\n{3,}/g, '\n\n').trim() : '选择器无匹配');
    }
    if (u.pathname === '/cmd/click') {
      const el = findButton(q);
      if (!el) return result({ ok: false, msg: '未找到目标按钮: ' + (q.text || q.id) });
      const label = (el.textContent || el.value || el.id || '').replace(/\s+/g, ' ').trim().slice(0, 60);
      el.click();
      return wait(400).then(() => result({ ok: true, clicked: label })).then(r => send(r));
    }
    if (u.pathname === '/cmd/set') {
      const el = dom.window.document.getElementById(q.id);
      if (!el) return result({ ok: false, msg: '无此元素 #' + q.id });
      if (el.tagName === 'SELECT') { el.value = q.value; el.dispatchEvent(new dom.window.Event('change', { bubbles: true })); }
      else if (el.type === 'checkbox') { el.checked = q.value === 'true' || q.value === '1'; el.dispatchEvent(new dom.window.Event('change', { bubbles: true })); }
      else { el.value = q.value; el.dispatchEvent(new dom.window.Event('input', { bubbles: true })); el.dispatchEvent(new dom.window.Event('change', { bubbles: true })); }
      return wait(300).then(() => result({ ok: true, set: q.id + ' = ' + q.value })).then(r => send(r));
    }
    if (u.pathname === '/cmd/wait') return wait(Math.min(parseInt(q.ms || '1000', 10), 120000)).then(() => result({ waited: 'ok' })).then(r => send(r));
    if (u.pathname === '/cmd/log') return send(['== console.error ==', ...errors.slice(-30), '== log 尾部 ==', ...logs.slice(-15)].join('\n') || '(空)');
    if (u.pathname === '/cmd/ls') {
      const ls = dom.window.localStorage; const o = {};
      for (let i = 0; i < ls.length; i++) { const k = ls.key(i); o[k] = (ls.getItem(k) || '').slice(0, 200); }
      return send(JSON.stringify(o, null, 1));
    }
    if (u.pathname === '/cmd/save') return send(result({ saved: true }));
    if (u.pathname === '/cmd/reload') {
      saveState();
      dom.window.close(); dom = bootJsdom();
      return wait(800).then(() => result({ ok: true, msg: '已重载(保留存档)' })).then(r => send(r));
    }
    if (u.pathname === '/cmd/reset') {
      try { fs.unlinkSync(STATE_FILE); } catch {}
      dom.window.close(); dom = bootJsdom();
      return wait(800).then(() => result({ ok: true, msg: '已完全重置' })).then(r => send(r));
    }
    return send('未知命令', 'text/plain', 404);
  } catch (e) {
    return send('驱动器异常: ' + e.stack, 'text/plain', 500);
  }
});

server.listen(PORT, '0.0.0.0', () => {
  dom = bootJsdom();
  console.log(`driver up: http://127.0.0.1:${PORT}/cmd/ui`);
});
setInterval(saveState, 15000);

/*
 * 构建与运行（在仓库外或临时目录执行，避免污染仓库）：
 *   mkdir -p /tmp/s2build && cd /tmp/s2build
 *   SRC=<仓库>/web/static/s2-vnext
 *   cp $SRC/{app.js,engine.js,voyage.js,description.js,game_data.json} .
 *   npx esbuild app.js --bundle --format=iife --outfile=bundle.js
 *   # 为 import 的带 query 文件名建立符号链接（esbuild 已解析依赖，运行时 fetch 不再需要）
 *   node <仓库>/tools/s2_playtest_driver.mjs /tmp/s2build 8222
 * API：
 *   /cmd/stats                  关键数值面板
 *   /cmd/ui?sel=#techTree       可访问性 UI 树（按钮/文本/禁用态）
 *   /cmd/click?id=xxx|text=xxx  点击按钮（text 为 URL 编码的包含匹配，n 选第几个）
 *   /cmd/set?id=xxx&value=xxx   设置 select/checkbox/input
 *   /cmd/read?sel=xxx           读元素文本
 *   /cmd/log                    页面 console 错误与日志
 *   /cmd/reload | /cmd/reset    重载(保留存档) | 清档重开
 */
