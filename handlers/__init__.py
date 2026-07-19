"""
handlers 子包 — 所有 bot 命令 handler 的集合。

每个子模块通过装饰器 @xxx_matcher.handle() 向 matchers.py 中定义的
Matcher 注册处理函数。导入本包即触发注册。
"""

from . import announcement, backpack, cat_park, fishing, gm, misc, shop, web
