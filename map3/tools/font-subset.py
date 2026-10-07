#!/usr/bin/env python3
"""把仓库自带的像素字体按 map3 实际用到的字符做子集化，产出小体积 woff2（附带 ttf 兜底）。"""
import glob, os, sys
from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_FONT = os.path.join(ROOT, '..', 'resources', 'fonts', 'HYPixel11pxU-2.ttf')
OUT_DIR = os.path.join(ROOT, 'assets')

chars = set()
for pat in ('**/*.js', '**/*.html', '**/*.md', '**/*.json'):
    for f in glob.glob(os.path.join(ROOT, pat), recursive=True):
        if '/assets/' in f:
            continue
        try:
            chars |= set(open(f, encoding='utf-8').read())
        except Exception:
            pass
# 常用补充字符，防止后续动态文案缺字
chars |= set('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
             ' ·—…、。，：；！？（）【】《》+-×÷=%°/\\|<>[]{}#@&*^~`\'",.:;!?')
chars |= set('猫鼠远洋舰队战斗等级胜利率护盾灼烧中毒引爆嘲讽晕眩冰冻易伤破防降攻降速追击散弹处决充能'
             '船员补给航行要塞攻坚猫港锈齿浅滩煤烟海峡油污湾废铁环礁毒雾沼泽齿轮暗流蒸汽风暴角灰烬深海鼠王钢堡')
text = ''.join(sorted(chars))
print('子集字符数:', len(text))

os.makedirs(OUT_DIR, exist_ok=True)
for fmt, name in (('woff2', 'HYPixel-subset.woff2'), ('ttf', 'HYPixel-subset.ttf')):
    try:
        subset.main([SRC_FONT, '--text=' + text, '--flavor=' + fmt if fmt == 'woff2' else '--text=' + text,
                     '--output-file=' + os.path.join(OUT_DIR, name), '--layout-features=*', '--no-hinting'])
        print(' 生成', name, os.path.getsize(os.path.join(OUT_DIR, name)) // 1024, 'KB')
    except Exception as e:
        print(' 失败', fmt, e)
