/* 把 index.html + src/*.js 内联成单文件 simulator.html（可离线 / 沙箱预览） */
const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..');
let html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const files = ['src/data.js', 'src/engine.js', 'src/ui.js'];
const tags = files.map(f => '<script src="' + f + '"></script>').join('\n');
if (!html.includes(tags)) throw new Error('未找到脚本标签组，index.html 结构已变化');
const inlined = files.map(f => {
  const code = fs.readFileSync(path.join(root, f), 'utf8')
    .replace(/<\/script>/g, '<\\/script>');
  return '<!-- inlined: ' + f + ' -->\n<script>\n' + code + '\n</script>';
}).join('\n');
/* 像素字体内联为 data URI，保证单文件离线可用 */
const fontPath = path.join(root, 'assets', 'HYPixel-subset.woff2');
if (fs.existsSync(fontPath)) {
  const b64 = fs.readFileSync(fontPath).toString('base64');
  html = html.replace('url("assets/HYPixel-subset.woff2") format("woff2")',
    'url(data:font/woff2;base64,' + b64 + ') format("woff2")');
}
html = html.replace(tags, inlined).replace('\n<!-- build:inline -->', '')
  .replace('<title>', '<title>').replace('map3 BATTLE SIM', 'map3 BATTLE SIM · 单文件版');
fs.writeFileSync(path.join(root, 'simulator.html'), html);
console.log('map3/simulator.html 已生成：', (html.length / 1024).toFixed(1) + 'KB');
