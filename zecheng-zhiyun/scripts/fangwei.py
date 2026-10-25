#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fangwei.py · 择城知运 · 方位 + 地域五行计算器

用途：以「当前城市」为太极点，计算候选城市相对它的方位角、八方/二十四山方位、
距离、方位五行；同时查该城市所属古九州与州五行，并给出「方位 vs 州五行」是否同向。

设计原则：
  1. 只做算术与查表，不做吉凶判断。吉凶取决于喜用校验（SKILL 第二步）。
  2. 方位与地域**分两栏**输出，永不合并。冲突时照实写"相反"。
  3. 归属有争议的州（如冀/幽之争）如实列两个候选，不替用户选一个。
  4. 九州之外的城市直接标"无甲级州五行"，不许硬套邻近州。

用法：
  python fangwei.py --from 上海 --to 成都 深圳 北京
  python fangwei.py --from 上海 --to 成都 北京 --card      # 输出 03 §11 格式城市卡
  python fangwei.py --zhou 北京                            # 只查州归属
  python fangwei.py --from 上海 --to-lat 30.57 --to-lon 104.07
  python fangwei.py --want 木 火                           # 反查：喜木火该往哪几个方位
  python fangwei.py --list                                 # 列出内置城市
  python fangwei.py --from 上海 --to 成都 --json            # 输出 JSON

依赖：仅标准库。
"""

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CITY_FILE = os.path.join(HERE, "cities.json")
ZHOU_FILE = os.path.join(HERE, "zhou.json")

# ---------------------------------------------------------------- 常量表

# 八方位：中心角（0=正北，顺时针）
# 方位五行依《五行大义·论八卦八风》"乾兑为金，坎为水，震巽为木，离为火，坤艮为土，各以方位言之"
SECTORS8 = [
    ("北",   "坎",   "水",   0.0),
    ("东北", "艮",   "土",   45.0),
    ("东",   "震",   "木",   90.0),
    ("东南", "巽",   "木",   135.0),
    ("南",   "离",   "火",   180.0),
    ("西南", "坤",   "土",   225.0),
    ("西",   "兑",   "金",   270.0),
    ("西北", "乾",   "金",   315.0),
]

# 二十四山：从正北起，每 15° 一山，顺时针
MOUNTAINS24 = [
    ("子", "水", "北"), ("癸", "水", "北"), ("丑", "土", "东北"), ("艮", "土", "东北"),
    ("寅", "木", "东北"), ("甲", "木", "东"), ("卯", "木", "东"), ("乙", "木", "东"),
    ("辰", "土", "东南"), ("巽", "木", "东南"), ("巳", "火", "东南"), ("丙", "火", "南"),
    ("午", "火", "南"), ("丁", "火", "南"), ("未", "土", "西南"), ("坤", "土", "西南"),
    ("申", "金", "西南"), ("庚", "金", "西"), ("酉", "金", "西"), ("辛", "金", "西"),
    ("戌", "土", "西北"), ("乾", "金", "西北"), ("亥", "水", "西北"), ("壬", "水", "北"),
]

BOUNDARY_WARN_DEG = 3.0
SAME_CITY_KM = 50.0      # 不足此距离，方位角无意义
NEAR_RING_KM = 80.0      # 同城圈：日常通勤可达，不构成迁居
REGION_KM = 300.0        # 邻域：可通勤式过渡；超过此值算实质迁居


def move_kind(dist):
    """迁居性质分档。距离决定"这算不算搬家"，与方位五行无关。"""
    if dist < SAME_CITY_KM:
        return "同城/近邻"
    if dist < NEAR_RING_KM:
        return "同城圈（不构成迁居）"
    if dist < REGION_KM:
        return "邻域（可通勤式过渡）"
    return "实质迁居"

# ---------------------------------------------------------------- 数据加载

_ALIAS = {}
_AMBIG = {}


def load_cities(path=CITY_FILE):
    """加载城市库。V2.0 起支持 _alias（全名→键）与 _ambiguous（歧义名→候选键列表）。"""
    global _ALIAS, _AMBIG
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    out = {}
    for group, items in raw.items():
        if group.startswith("_"):
            continue
        for name, coord in items.items():
            out[name] = {"lat": float(coord[0]), "lon": float(coord[1]), "group": group}
    _ALIAS = {k: v for k, v in (raw.get("_alias") or {}).items() if v in out}
    _AMBIG = {k: [x for x in v if x in out] for k, v in (raw.get("_ambiguous") or {}).items()}
    return out


def load_zhou(path=ZHOU_FILE):
    """返回 (州五行 dict, 城市 dict)。文件缺失时降级为全空，不报错中断。"""
    if not os.path.exists(path):
        return {}, {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return raw.get("州五行", {}), raw.get("城市", {})


def _strip(name):
    s = name
    for suf in ("特别行政区", "自治区", "自治州", "自治县", "地区", "市辖区", "省", "市", "县", "区", "盟", "旗"):
        if s.endswith(suf) and len(s) > len(suf) + 1:
            return s[: -len(suf)]
    return s


def resolve(name, cities):
    """城市名解析：精确 → 去后缀 → 别名（全名）→ 歧义提示 → 前缀唯一 → 包含唯一。

    V2.0 起库内有 3200+ 条，含大量同名区县。宁可报错让人写全，也不静默取一个。
    """
    name = (name or "").strip()
    if name in cities:
        return name, cities[name]
    st = _strip(name)
    if st in cities:
        return st, cities[st]
    for cand in (name, st):
        if cand in _ALIAS and _ALIAS[cand] in cities:
            return _ALIAS[cand], cities[_ALIAS[cand]]
    # 歧义名：直接给候选，不猜
    if st in _AMBIG and st not in cities:
        cands = sorted(_AMBIG[st])
        raise SystemExit("「%s」在库中有 %d 个同名行政区：%s。\n请写「市名+区名」形式（如 南京鼓楼），或用 --to-lat/--to-lon 直接给坐标。"
                         % (name, len(cands), "、".join(cands[:10])))
    # 前缀匹配：取最短（通常就是本级行政区）
    pref = sorted([k for k in cities if k.startswith(st)], key=lambda x: (len(x), x))
    if len(pref) == 1:
        return pref[0], cities[pref[0]]
    if pref:
        if len(pref[0]) < len(pref[1]):
            return pref[0], cities[pref[0]]
        raise SystemExit("「%s」匹配到多个城市：%s。请写得更具体。" % (name, "、".join(pref[:8])))
    hits = [k for k in cities if st in k]
    if len(hits) == 1:
        return hits[0], cities[hits[0]]
    if len(hits) > 1:
        raise SystemExit("「%s」匹配到多个城市：%s。请写全名，或用 --to-lat/--to-lon 直接给坐标。"
                         % (name, "、".join(sorted(hits)[:8])))
    raise SystemExit("内置城市库里没有「%s」。请用 --to-lat/--to-lon 直接给经纬度，"
                     "或先把该城市补进 scripts/cities.json（并在 zhou.json 里登记州属）。" % name)



# ---------------------------------------------------------------- 计算

def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing(lat1, lon1, lat2, lon2):
    """大圆初始方位角：0=正北，90=正东，顺时针 0-360"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def sector8(deg):
    """返回 (方位, 卦, 五行, 中心角, 距边界度数)"""
    best = min(SECTORS8, key=lambda s: abs(((deg - s[3] + 180) % 360) - 180))
    off = abs(((deg - best[3] + 180) % 360) - 180)
    to_edge = 22.5 - off
    return best[0], best[1], best[2], best[3], to_edge


def mountain24(deg):
    idx = int(round(deg / 15.0)) % 24
    name, wx, sec = MOUNTAINS24[idx]
    center = idx * 15.0
    off = abs(((deg - center + 180) % 360) - 180)
    return name, wx, sec, center, 7.5 - off


def sector8_alt(deg):
    """贴近扇区边界时，改判会是哪个方位。返回 (方位, 卦, 五行)。"""
    i = min(range(len(SECTORS8)), key=lambda k: abs(((deg - SECTORS8[k][3] + 180) % 360) - 180))
    d = ((deg - SECTORS8[i][3] + 180) % 360) - 180
    j = (i - 1) % 8 if d < 0 else (i + 1) % 8
    return SECTORS8[j][0], SECTORS8[j][1], SECTORS8[j][2]


def mountain24_alt(deg):
    """贴近二十四山分界时，改判会是哪一山。返回 (山, 五行)。"""
    idx = int(round(deg / 15.0)) % 24
    d = ((deg - idx * 15.0 + 180) % 360) - 180
    j = (idx - 1) % 24 if d < 0 else (idx + 1) % 24
    return MOUNTAINS24[j][0], MOUNTAINS24[j][1]


# ---------------------------------------------------------------- 州判定

def zhou_info(city_name, zhou_map, wx_map):
    """返回州归属信息 dict：档（定/议/外）、候选州、五行、说明、源（人工核定/批量推演）"""
    rec = zhou_map.get(city_name)
    if rec is None:
        return {"档": "缺", "候选": [], "说明": "zhou.json 未登记此城，州归属未知", "源": ""}
    src = rec.get("源", "")
    cands = rec.get("州", [])
    if not cands:
        return {"档": "外", "候选": [], "源": src,
                "说明": "九州之外（《禹贡》系统无对应州），地域五行无甲级依据，只能走丙级地理取象"}
    items = []
    for z in cands:
        wx = wx_map.get(z)
        items.append({"州": z, "五行": wx})
    return {"档": rec.get("档", "定"), "候选": items, "注": rec.get("注", ""), "源": src}


def fmt_zhou(info):
    """把州信息压成一行文字。批量推演的条目带 ※ 标记，防止被当成甲级。"""
    if info["档"] == "外":
        s = "九州之外（无甲级）"
    elif info["档"] == "缺":
        s = "未登记（无甲级）"
    else:
        parts = []
        for it in info["候选"]:
            wx = it["五行"] if it["五行"] else "无甲级"
            parts.append("%s（%s）" % (it["州"], wx))
        s = " / ".join(parts)
        if info["档"] == "议":
            s += "  ← 归属有争议"
    if info.get("源") == "批量推演":
        s += " ※批量推演"
    return s


def compare(wx_fangwei, info):
    """方位五行 vs 州五行 → 同向 / 相反 / 无法比较"""
    wxs = [it["五行"] for it in info["候选"] if it["五行"]]
    if not wxs:
        return "无法比较（州五行缺）"
    disputed = info.get("档") == "议"
    if len(set(wxs)) == 1:
        base = "同向" if wxs[0] == wx_fangwei else "相反"
        # 争议州里若另一候选无甲级，须注明，不许只说同向
        if disputed and len(wxs) < len(info["候选"]):
            return base + "（另一候选无甲级）"
        return base
    if wx_fangwei in wxs:
        return "一同一异（归属有争议）"
    return "相反（两候选均不同）"


# ---------------------------------------------------------------- 输出

def analyze(origin, targets, as_json=False, as_card=False, zhou_map=None, wx_map=None):
    zhou_map = zhou_map or {}
    wx_map = wx_map or {}
    o_name, o = origin
    rows = []
    for t_name, t in targets:
        info = zhou_info(t_name, zhou_map, wx_map)
        dist = haversine(o["lat"], o["lon"], t["lat"], t["lon"])
        if dist < SAME_CITY_KM:
            rows.append({
                "目标": t_name, "距离km": round(dist, 1), "迁居性质": move_kind(dist),
                "方位角": None, "八方": "同城/近邻", "卦": "—", "方位五行": "—",
                "二十四山": "—", "州": fmt_zhou(info), "州档": info["档"],
                "关系": "—", "提示": "距离不足 50km，方位无意义，按同城处理",
                "_info": info,          # V2.1.4 修：同城分支漏传州信息，卡片误报"未登记此城"
                "_b": None, "_s_edge": 0.0, "_m_edge": 0.0,
            })
            continue
        b = bearing(o["lat"], o["lon"], t["lat"], t["lon"])
        s_name, gua, wx, s_center, s_edge = sector8(b)
        m_name, m_wx, m_sec, m_center, m_edge = mountain24(b)
        tips_geo = []   # 方位层提示，卡片里单独一行
        tips_zhou = []  # 州层提示，卡片里已由【地域五行】段承担，避免重复
        if s_edge < BOUNDARY_WARN_DEG:
            a_name, a_gua, a_wx = sector8_alt(b)
            tips_geo.append("距八方分界仅 %.1f°，方位归属不稳；若改判则为 %s·%s·%s" % (s_edge, a_name, a_gua, a_wx))
        if m_edge < 1.5:
            a_m, a_mw = mountain24_alt(b)
            tips_geo.append("距二十四山分界仅 %.1f°，细分山向不稳；若改判则为 %s（%s）" % (m_edge, a_m, a_mw))
        if wx != m_wx:
            tips_geo.append("两层不一致：八卦层%s（%s）／二十四山%s（%s），本表以八卦层为准，改用山向须重判"
                            % (gua, wx, m_name, m_wx))
        if t.get("group") == "海外":
            tips_geo.append("境外城市：方位可算，但地域五行无古籍依据（见 03 号文件 §6）")
        if info["档"] == "议":
            tips_zhou.append("州归属有争议（%s），两候选并列，不替用户选" % (info.get("注") or "两系统之说"))
        if info["档"] == "外" and t.get("group") != "海外":
            # 境外已在方位提示里说过"地域无依据"，此处不重复
            tips_zhou.append("九州之外，地域五行无甲级依据")
        tips = tips_geo + tips_zhou
        rows.append({
            "目标": t_name, "距离km": round(dist, 1), "迁居性质": move_kind(dist),
            "方位角": round(b, 1), "八方": s_name, "卦": gua, "方位五行": wx,
            "二十四山": "%s（%s）" % (m_name, m_wx),
            "州": fmt_zhou(info), "州档": info["档"],
            "关系": compare(wx, info),
            "提示": "；".join(tips) if tips else "",
            "_info": info, "_b": b, "_s_edge": s_edge, "_m_edge": m_edge,
            "_m_name": m_name, "_m_wx": m_wx, "_tips_geo": "；".join(tips_geo),
        })

    if as_json:
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
        print(json.dumps({"原点": o_name, "结果": clean}, ensure_ascii=False, indent=2))
        return

    if as_card:
        print_cards(o_name, o, rows)
        return

    print("## 方位与地域：以「%s」为太极点（%.2f, %.2f）\n" % (o_name, o["lat"], o["lon"]))
    print("| 目标城市 | 距离 km | 迁居性质 | 方位角 | 八方位 | 卦 | 方位五行 | 二十四山 | 所属州（州五行） | 两栏关系 | 提示 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        ang = "—" if r["方位角"] is None else "%.1f°" % r["方位角"]
        print("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["目标"], r["距离km"], r["迁居性质"], ang, r["八方"], r["卦"], r["方位五行"],
            r["二十四山"], r["州"], r["关系"], r["提示"] or "—"))
    print()
    print("> 方位角为从原点出发的大圆初始方位角（0°=正北，顺时针）。")
    print("> 方位五行依《五行大义·论八卦八风》：乾兑金、坎水、震巽木、离火、坤艮土。")
    print("> 州五行依《三命通会》卷四得地条：木兖青、火徐扬、土豫、金荆梁、水冀雍。")
    print("> **迁居性质**按距离分档：<50km 同城/近邻（方位无意义）｜50–80km 同城圈（不构成迁居）"
          "｜80–300km 邻域（可通勤式过渡）｜>300km 实质迁居。距离与方位五行无关，是两回事。")
    print("> **两栏关系**：同向可写\"可信度较高\"；相反必须并列，不许合并（03 §9.4）。")
    print("> 此表不给吉凶。是否宜往，取决于喜用校验（SKILL 第二、三步）与本命交叉（03a §4）。")


def print_cards(o_name, o, rows):
    """按 03 号文件 §11 的格式输出城市卡"""
    print("# 城市卡 · 以「%s」为太极点\n" % o_name)
    for r in rows:
        print("```")
        print("城市：%s" % r["目标"])
        if r["方位角"] is None:
            print("【方位】与「%s」距离 %s km（%s），不足 50km，按同城处理，方位无意义" % (
                o_name, r["距离km"], r["迁居性质"]))
        else:
            print("【方位】相对%s：%.1f°，%s·%s·%s（距边界 %.1f°）" % (
                o_name, r["_b"], r["八方"], r["卦"], r["方位五行"], r["_s_edge"]))
            print("        二十四山：%s（距边界 %.1f°）" % (r["二十四山"], r["_m_edge"]))
            print("        距离：%s km｜迁居性质：%s" % (r["距离km"], r["迁居性质"]))
            print("        依据：几何计算 + 《五行大义》方位五行｜等级：甲｜置信：高")
        if r.get("_tips_geo"):
            print("        方位提示：%s" % r["_tips_geo"])
        info = r.get("_info", {})
        print("【地域五行】%s" % r["州"])
        if info.get("源"):
            print("        依据来源：%s%s" % (
                info["源"],
                "（按省规则+市例外推导，未经逐县考证）" if info["源"] == "批量推演" else "（逐城核对过）"))
        if info.get("档") == "定":
            z = info["候选"][0]
            print("        州五行：%s ——《三命通会》卷四得地条｜等级：甲" % z["五行"])
            print("        城市→州归属：乙级推演（古今政区不可完全对齐）｜置信：中")
        elif info.get("档") == "议":
            print("        ⚠ 归属有争议：%s" % (info.get("注") or "两系统之说（禹贡与周礼对不上）"))
            print("        两候选并列，本脚本不替选。报告里必须两个都写。｜置信：中偏低")
        elif info.get("档") == "外":
            print("        州五行：无甲级依据（九州之外）")
            print("        只能走丙级地理取象（03 §6），需 ≥2 条同向才可下「弱判断」")
        else:
            print("        ⚠ zhou.json 未登记此城，州归属未知，须手工补登后再判")
        if r["方位角"] is not None:
            print("【两栏关系】%s" % r["关系"])
        print("【本命交叉】脚本不代判。查 03a §4 的\"日主五行 × 月令段\"表，")
        print("            取该格吉州/凶州，与本城所属州比对。")
        print("            必须带转换声明：卷四断语按**日主**判，本技能按**喜用**判（03a §6.2）。")
        print("```")
        print()


def reverse_lookup(wants, origin=None):
    print("## 反查：喜「%s」→ 可考虑的方位\n" % "、".join(wants))
    want_set = set(wants)
    hits8 = [s for s in SECTORS8 if s[2] in want_set]
    if hits8:
        print("**八方位层（粗选）**\n")
        print("| 方位 | 卦 | 五行 | 中心方位角 | 覆盖角度 |")
        print("| --- | --- | --- | --- | --- |")
        for name, gua, wx, c in hits8:
            print("| %s | %s | %s | %d° | %d°–%d° |" % (
                name, gua, wx, int(c), int((c - 22.5) % 360), int((c + 22.5) % 360)))
        print()
    hits24 = [(n, w, s) for n, w, s in MOUNTAINS24 if w in want_set]
    if hits24:
        print("**二十四山层（细分）**\n")
        print("| 山 | 五行 | 所属八方 | 中心方位角 |")
        print("| --- | --- | --- | --- |")
        for i, (n, w, s) in enumerate(MOUNTAINS24):
            if w in want_set:
                print("| %s | %s | %s | %d° |" % (n, w, s, i * 15))
        print()

    # 州层：反查哪些州的五行命中
    wx_map, _ = load_zhou()
    zhou_hits = [z for z, w in wx_map.items() if w in want_set]
    if zhou_hits:
        print("**州五行层（地域，与方位不是一回事）**\n")
        print("| 州 | 五行 | 现代大致范围 |")
        print("| --- | --- | --- |")
        scope = {
            "冀州": "河北中南部、山西、内蒙中南部", "兖州": "山东西部、河南东北部",
            "青州": "山东半岛", "徐州": "苏北、鲁南、皖东北", "扬州": "苏南、浙江、福建、江西、上海、广东、广西",
            "荆州": "湖北、湖南", "豫州": "河南大部、皖西北", "梁州": "川东、重庆、陕南、云贵",
            "雍州": "陕西、甘肃东部、宁夏",
        }
        for z in zhou_hits:
            print("| %s | %s | %s |" % (z, wx_map[z], scope.get(z, "—")))
        print()
        print("> 注意：州五行回答的是\"这片地方本身是什么气\"，方位五行回答的是\"朝哪个方向走\"。")
        print("> 两者在东南/西南/西北三处结论相反（03 §9.4），**不可互相印证**。")

    print("> 同一方位常跨两个五行（如东南属巽木、西南属坤土）。挑选时优先取「五行纯度高」的方位：")
    print("> 正东=纯木、正南=纯火、正西=纯金、正北=纯水；四维（东北/东南/西南/西北）为土或杂气。")


def show_zhou(name, cities, zhou_map, wx_map):
    n, _ = resolve(name, cities)
    info = zhou_info(n, zhou_map, wx_map)
    rec = zhou_map.get(n, {})
    print("## 州归属查询：%s\n" % n)
    if rec.get("全名"):
        parts = []
        for p in (rec.get("省"), rec.get("市"), rec.get("全名")):
            if p and p not in parts:
                parts.append(p)
        path = "·".join(parts)
        print("- 行政：%s（%s）" % (path, {"city": "地级市", "district": "县级", "county": "台湾县市", "overseas": "境外"}.get(rec.get("级"), "—")))
    print("- 档位：**%s**（定=无争议 / 议=有争议 / 外=九州之外）" % info["档"])
    if info.get("源"):
        print("- 依据来源：**%s**%s" % (info["源"], "（按省规则+市例外推导，未经逐县考证）" if info["源"] == "批量推演" else "（逐城核对过）"))
    if info.get("注"):
        print("- 说明：%s" % info["注"])
    if info["候选"]:
        print("\n| 候选州 | 州五行 | 出处 |")
        print("| --- | --- | --- |")
        for it in info["候选"]:
            src = "《三命通会》卷四得地条" if it["五行"] else "不在九州之内，无甲级"
            print("| %s | %s | %s |" % (it["州"], it["五行"] or "—", src))
    else:
        print("- 结论：**九州之外，无甲级州五行**。只能走丙级地理取象（03 §6）。")
    print()
    print("> 州五行是甲级；\"这座城市归哪个州\"是乙级推演。整链置信取最低一环。")
    if info.get("源") == "批量推演":
        print("> ※ 本条为**批量推演**：按「省规则 + 市例外 + 区县继承所属市」推导，**未经逐县考证**，不得当作甲级依据引用。")


def main():
    ap = argparse.ArgumentParser(description="择城知运 · 方位 + 地域五行计算器", add_help=True)
    ap.add_argument("--from", dest="origin_name", help="原点城市（当前长期居住城市）")
    ap.add_argument("--from-lat", type=float, help="原点纬度")
    ap.add_argument("--from-lon", type=float, help="原点经度")
    ap.add_argument("--to", nargs="+", default=[], help="一个或多个目标城市")
    ap.add_argument("--to-lat", type=float, help="目标纬度（仅单目标时用）")
    ap.add_argument("--to-lon", type=float, help="目标经度（仅单目标时用）")
    ap.add_argument("--want", nargs="+", default=[], help="反查：喜用五行，如 --want 木 火")
    ap.add_argument("--zhou", help="只查某城的州归属与州五行")
    ap.add_argument("--card", action="store_true", help="按 03 §11 格式输出城市卡")
    ap.add_argument("--list", action="store_true", help="列出内置城市（按省级汇总）")
    ap.add_argument("--list-prov", dest="list_prov", help="列出某省级单位下的全部城市，如 --list-prov 江苏")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    cities = load_cities()
    wx_map, zhou_map = load_zhou()

    if args.list:
        from collections import Counter
        cn = [k for k, v in cities.items() if v["group"] == "中国"]
        os_ = [k for k, v in cities.items() if v["group"] == "海外"]
        print("[中国] %d 条（含地级市与县级行政区）" % len(cn))
        print("[海外] %d 条：%s" % (len(os_), "、".join(sorted(os_))))
        lv = Counter(zhou_map.get(k, {}).get("级") for k in cn)
        src = Counter(zhou_map.get(k, {}).get("源") for k in cn)
        print("[层级] " + "，".join("%s %d" % (k or "未标", v) for k, v in lv.items()))
        print("[来源] " + "，".join("%s %d" % (k or "未标", v) for k, v in src.items()))
        # 按省列出，避免三千条刷屏
        byp = {}
        for k in cn:
            p = zhou_map.get(k, {}).get("省") or "未标"
            byp.setdefault(p, []).append(k)
        print("\n按省级单位（只列前 12 个，用 --list-prov 查看全部）：")
        for p in sorted(byp)[:12]:
            print("  %s：%d 条" % (p, len(byp[p])))
        missing = [k for k in cities if k not in zhou_map]
        if missing:
            print("\n[未登记州属] %d 城：%s" % (len(missing), "、".join(sorted(missing)[:20])))
        else:
            print("\n[未登记州属] 0 条")
        return

    if args.list_prov:
        byp = {}
        for k in cities:
            p = zhou_map.get(k, {}).get("省") or "未标"
            byp.setdefault(p, []).append(k)
        p = args.list_prov
        hit = [x for x in byp if p in x]
        if not hit:
            print("没有匹配的省级单位：%s" % p)
            return
        for x in hit:
            print("[%s] %d 条：%s" % (x, len(byp[x]), "、".join(sorted(byp[x]))))
        return

    if args.zhou:
        show_zhou(args.zhou, cities, zhou_map, wx_map)
        return

    if args.want:
        reverse_lookup(args.want)
        return

    # 原点
    if args.origin_name:
        o_name, o = resolve(args.origin_name, cities)
    elif args.from_lat is not None and args.from_lon is not None:
        o_name, o = "指定坐标", {"lat": args.from_lat, "lon": args.from_lon, "group": "自定义"}
    else:
        raise SystemExit("请用 --from 城市名，或 --from-lat/--from-lon 指定原点。")

    # 目标
    targets = []
    for name in args.to:
        n, c = resolve(name, cities)
        targets.append((n, c))
    if args.to_lat is not None and args.to_lon is not None:
        targets.append(("指定坐标", {"lat": args.to_lat, "lon": args.to_lon, "group": "自定义"}))
    if not targets:
        raise SystemExit("请用 --to 城市名（可多个），或 --to-lat/--to-lon 指定目标。")

    analyze((o_name, o), targets, as_json=args.json, as_card=args.card,
            zhou_map=zhou_map, wx_map=wx_map)


if __name__ == "__main__":
    main()
