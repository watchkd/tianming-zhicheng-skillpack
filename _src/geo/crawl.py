# -*- coding: utf-8 -*-
"""抓取阿里云 DataV.GeoAtlas 行政区划（省/市/区县三级，含中心点坐标）

输出：_src/geo/areas.json
  结构：[{adcode, name, level, center:[lng,lat], province, city}]
"""
import json
import io
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://geo.datav.aliyun.com/areas_v3/bound/%d_full.json"
OUT = "_src/geo/areas.json"
CACHE = "_src/geo/cache"
os.makedirs(CACHE, exist_ok=True)


def fetch(adcode, retry=3):
    path = os.path.join(CACHE, "%d.json" % adcode)
    if os.path.exists(path) and os.path.getsize(path) > 200:
        return json.load(io.open(path, encoding="utf-8"))
    url = BASE % adcode
    last = None
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8")
            if not raw.strip().startswith("{"):
                raise ValueError("非 JSON 响应")
            d = json.loads(raw)
            io.open(path, "w", encoding="utf-8").write(raw)
            return d
        except Exception as e:
            last = e
            time.sleep(1.2 * (i + 1))
    print("  失败", adcode, last)
    return None


def props(feat):
    p = feat.get("properties") or {}
    return {
        "adcode": p.get("adcode"),
        "name": p.get("name"),
        "level": p.get("level"),
        "center": p.get("center"),
        "childrenNum": p.get("childrenNum", 0),
    }


def main():
    print("1) 省级")
    top = fetch(100000)
    if not top:
        print("省级失败，退出")
        return
    provinces = [props(f) for f in top["features"]]
    print("   省 %d" % len(provinces))

    print("2) 省级下一级（市 / 直辖市的区）")
    tasks = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for p in provinces:
            if p["childrenNum"]:
                tasks[ex.submit(fetch, p["adcode"])] = p
        level2 = {}
        for fu in as_completed(tasks):
            p = tasks[fu]
            d = fu.result()
            if not d:
                continue
            level2[p["adcode"]] = [props(f) for f in d["features"]]
    total2 = sum(len(v) for v in level2.values())
    print("   二级 %d" % total2)

    print("3) 市级下一级（区县）")
    need = []
    for pcode, items in level2.items():
        for it in items:
            if it["childrenNum"] and it["level"] != "district":
                need.append(it)
    print("   需抓取 %d 个" % len(need))
    level3 = {}
    done = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        tasks = {ex.submit(fetch, it["adcode"]): it for it in need}
        for fu in as_completed(tasks):
            it = tasks[fu]
            d = fu.result()
            done += 1
            if done % 50 == 0:
                print("   ... %d/%d" % (done, len(need)))
            if not d:
                continue
            level3[it["adcode"]] = [props(f) for f in d["features"]]
    print("   三级 %d" % sum(len(v) for v in level3.values()))

    # 组装
    recs = []
    for p in provinces:
        recs.append({
            "adcode": p["adcode"], "name": p["name"], "level": "province",
            "center": p["center"], "province": p["name"], "city": "",
        })
        for c in level2.get(p["adcode"], []):
            lvl = "district" if c["level"] == "district" else "city"
            recs.append({
                "adcode": c["adcode"], "name": c["name"], "level": lvl,
                "center": c["center"], "province": p["name"],
                "city": "" if lvl == "district" else c["name"],
            })
            if lvl == "city":
                for d in level3.get(c["adcode"], []):
                    recs.append({
                        "adcode": d["adcode"], "name": d["name"], "level": "district",
                        "center": d["center"], "province": p["name"], "city": c["name"],
                    })

    json.dump(recs, io.open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    from collections import Counter
    print("写出 %s，共 %d 条" % (OUT, len(recs)))
    print(Counter(r["level"] for r in recs))
    nocenter = [r["name"] for r in recs if not r["center"]]
    print("缺坐标 %d 条：%s" % (len(nocenter), nocenter[:20]))


if __name__ == "__main__":
    main()
