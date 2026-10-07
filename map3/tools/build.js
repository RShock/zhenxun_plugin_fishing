/* 把各页面 + src/*.js + 像素字体子集内联成单文件（可离线 / 沙箱预览） */
const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..');

const PAGES = [
  { src: 'index.html',   out: 'simulator.html', scripts: ['src/data.js', 'src/engine.js', 'src/ui.js'] },
  { src: 'gallery.html', out: 'heroes.html',    scripts: ['src/data.js', 'src/gallery.js'] }
];

const fontPath = path.join(root, 'assets', 'HYPixel-subset.woff2');
const fontB64 = fs.existsSync(fontPath) ? fs.readFileSync(fontPath).toString('base64') : null;

PAGES.forEach(function (page) {
  let html = fs.readFileSync(path.join(root, page.src), 'utf8');
  const tags = page.scripts.map(function (f) { return '<script src="' + f + '"></script>'; }).join('\n');
  if (!html.includes(tags)) throw new Error(page.src + '：未找到脚本标签组，结构可能已变化');
  const inlined = page.scripts.map(function (f) {
    const code = fs.readFileSync(path.join(root, f), 'utf8').replace(/<\/script>/g, '<\\/script>');
    return '<!-- inlined: ' + f + ' -->\n<script>\n' + code + '\n</script>';
  }).join('\n');
  html = html.replace(tags, inlined);
  if (fontB64) {
    html = html.replace('url("assets/HYPixel-subset.woff2") format("woff2")',
      'url(data:font/woff2;base64,' + fontB64 + ') format("woff2")');
  }
  fs.writeFileSync(path.join(root, page.out), html);
  console.log(page.out + '　' + (html.length / 1024).toFixed(1) + 'KB　（源: ' + page.src + '）');
});
