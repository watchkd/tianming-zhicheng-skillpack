# -*- coding: utf-8 -*-
"""提取上一轮被剔除的 10 个"未蒸馏"小节。显式给定起止行，避免跨卷目录行混入。"""
import os, re, json

SRC = r"C:/Users/PC/xwechat_files/wxid_sv0jv37mbo0j22_fd36/temp/RWTemp/2026-10/b135e1ddbfc84f7877251b3ff4e2759a/五行大义_殆知阁.txt"
BASE = r"C:/Users/PC/WorkBuddy/2026-10-25-14-45-26/蒸馏_五行大义"
OUT = os.path.join(BASE, "原文_续")
os.makedirs(OUT, exist_ok=True)

lines = open(SRC, encoding="utf-8").read().split("\n")

# (起, 止(不含), 标题, 文件名)
SEC = [
    (81,  85,  "起大衍论易动静数", "01_起大衍论易动静数"),
    (97,  100, "论九宫数",         "02_论九宫数"),
    (207, 211, "论律吕",           "03_论律吕"),
    (211, 215, "论七政",           "04_论七政"),
    (215, 218, "论八卦八风",       "05_论八卦八风"),
    (223, 234, "论治政",           "06_论治政"),
    (235, 238, "论诸神",           "07_论诸神"),
    (239, 242, "论五帝",           "08_论五帝"),
    (243, 246, "论诸官",           "09_论诸官"),
    (255, len(lines), "论禽虫",    "10_论禽虫"),
]

DROP = re.compile(r"^\s*(五行大义卷第|第[一二三四五六七八九十]+[论释辨明].*就此分为)")

total = 0
idx = []
for start, end, name, fn in SEC:
    body = [l for l in lines[start:end] if not DROP.match(l)]
    body = "\n".join(body).strip()
    open(os.path.join(OUT, fn + ".txt"), "w", encoding="utf-8").write(
        "《五行大义》续篇 · %s\n\n" % name + body)
    print("%-22s %6d 字" % (name, len(body)))
    total += len(body)
    idx.append({"section": name, "file": fn + ".txt", "chars": len(body)})

print("\n续篇字数合计: %d" % total)
json.dump({"total_chars": total, "sections": idx},
          open(os.path.join(BASE, "块索引_续.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
