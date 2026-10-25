# -*- coding: utf-8 -*-
"""V2.0 全国市县全覆盖构建脚本

输入：_src/geo/areas.json（DataV.GeoAtlas 抓取，3238 条）
      scripts/cities.json / scripts/zhou.json（V1.5 人工核定的 227 城，作为权威覆盖）
输出：scripts/cities.json（中国 3000+ + 海外 52）
      scripts/zhou.json（逐条登记 州 / 档 / 注 / 源）

设计原则：
1. 人工核定的 227 座优先，批量推演不得覆盖它们。
2. 批量推演的州归属按「省规则 + 市例外 + 区县继承所属市」三级推导，全部标 源=批量推演。
3. 重名一律消歧，歧义名单独登记，查询时提示候选而不是静默选一个。
"""
import json
import io
import os
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

AREAS = "_src/geo/areas.json"
CITY_FILE = "tianming-zhicheng/scripts/cities.json"
ZHOU_FILE = "tianming-zhicheng/scripts/zhou.json"

# ---------- 名称处理 ----------
SUFFIX = [
    "特别行政区", "维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "自治州", "自治县",
    "自治旗", "林区", "特区", "新区", "矿区", "地区", "盟", "市辖区",
    "市", "区", "县", "旗", "镇", "省",
]


ETHNIC = [
    "维吾尔", "柯尔克孜", "乌孜别克", "鄂温克", "鄂伦春", "达斡尔", "哈萨克", "塔吉克", "俄罗斯",
    "土家", "哈尼", "傈僳", "拉祜", "景颇", "纳西", "仫佬", "仡佬", "毛南", "撒拉", "布朗",
    "阿昌", "普米", "德昂", "保安", "裕固", "塔塔尔", "独龙", "赫哲", "门巴", "珞巴", "基诺",
    "蒙古", "朝鲜", "布依", "锡伯", "高山", "东乡",
    "白", "彝", "苗", "侗", "瑶", "壮", "藏", "回", "满", "傣", "黎", "佤", "畲", "水", "土", "羌", "怒", "京",
]


def short(name):
    """去掉行政级别后缀与民族名，得到口语名。如 大理白族自治州 → 大理。"""
    if not name:
        return ""
    s = name
    for suf in SUFFIX:
        if s.endswith(suf) and len(s) > len(suf) + 1:
            s = s[: -len(suf)]
            break
    # 反复剥掉结尾的「民族名+族」
    changed = True
    while changed:
        changed = False
        for e in ETHNIC:
            tok = e + "族"
            if s.endswith(tok) and len(s) > len(tok) + 1:
                s = s[: -len(tok)]
                changed = True
                break
    return s


# ---------- 省规则 ----------
# (州列表, 档, 注)
PROV = {
    "北京市": (["冀州", "幽州"], "议", "禹贡属冀；周礼职方氏为幽州"),
    "天津市": (["冀州", "幽州"], "议", "禹贡属冀；周礼职方氏为幽州"),
    "河北省": (["冀州"], "定", ""),
    "山西省": (["冀州", "并州"], "议", "禹贡属冀；周礼职方氏为并州"),
    "内蒙古自治区": (["冀州", "并州"], "议", "中南部属禹贡冀州；周礼并州，东部为九州外"),
    "辽宁省": (["冀州", "幽州"], "议", "辽西属禹贡冀州；周礼幽州"),
    "吉林省": ([], "外", "肃慎/扶余故地，九州之外"),
    "黑龙江省": ([], "外", "肃慎故地，九州之外"),
    "上海市": (["扬州"], "定", ""),
    "江苏省": (["扬州"], "定", ""),
    "浙江省": (["扬州"], "定", ""),
    "安徽省": (["扬州"], "定", ""),
    "福建省": (["扬州"], "定", ""),
    "江西省": (["扬州"], "定", ""),
    "山东省": (["兖州"], "定", ""),
    "河南省": (["豫州"], "定", ""),
    "湖北省": (["荆州"], "定", ""),
    "湖南省": (["荆州"], "定", ""),
    "广东省": (["扬州"], "定", "岭南，汉属交州，禹贡扬州南境"),
    "广西壮族自治区": (["扬州"], "定", "岭南，汉属交州，禹贡扬州南境"),
    "海南省": (["扬州"], "议", "海南为禹贡扬州徼外，汉置珠崖儋耳"),
    "重庆市": (["梁州"], "定", ""),
    "四川省": (["梁州"], "定", ""),
    "贵州省": (["梁州", "益州"], "议", "禹贡梁州南境；汉益州郡"),
    "云南省": (["梁州", "益州"], "议", "禹贡梁州南境；汉益州郡"),
    "西藏自治区": ([], "外", "吐蕃，九州之外"),
    "陕西省": (["雍州"], "定", ""),
    "甘肃省": (["雍州"], "定", ""),
    "青海省": (["雍州"], "定", "禹贡雍州西境；西部或谓九州外"),
    "宁夏回族自治区": (["雍州"], "定", ""),
    "新疆维吾尔自治区": ([], "外", "西域，九州之外"),
    "台湾省": (["扬州"], "议", "九州之外岛屿；一说古属扬州域外，两说并列"),
    "香港特别行政区": (["扬州"], "定", "古属扬州刺史部南海郡"),
    "澳门特别行政区": (["扬州"], "定", "古属扬州刺史部南海郡"),
}

# 市级例外：城市名（全名） -> (州, 档, 注)
CITY_EXC = {
    # 江苏
    "徐州市": (["徐州"], "定", "苏北，禹贡徐州"),
    "连云港市": (["徐州"], "定", "苏北，禹贡徐州"),
    "淮安市": (["徐州"], "定", "苏北，禹贡徐州"),
    "宿迁市": (["徐州"], "定", "苏北，禹贡徐州"),
    "盐城市": (["徐州", "扬州"], "议", "苏中，徐扬交界"),
    # 山东
    "青岛市": (["青州"], "定", "胶东半岛"),
    "烟台市": (["青州"], "定", "胶东半岛"),
    "威海市": (["青州"], "定", "胶东半岛"),
    "潍坊市": (["青州"], "定", "鲁中偏东"),
    "淄博市": (["青州"], "定", "鲁中"),
    "东营市": (["青州"], "定", "黄河口"),
    "临沂市": (["徐州"], "定", "鲁南，禹贡徐州"),
    "日照市": (["徐州"], "定", "鲁东南，禹贡徐州"),
    # 河南
    "南阳市": (["荆州"], "定", "豫西南，汉荆州刺史部"),
    "信阳市": (["荆州", "豫州"], "议", "豫南，荆豫交界"),
    "安阳市": (["冀州", "豫州"], "议", "豫北，冀豫交界"),
    # 安徽
    "合肥市": (["扬州", "豫州"], "议", "江淮之间，扬豫交界"),
    "淮北市": (["徐州", "豫州"], "议", "皖北，徐豫交界"),
    "宿州市": (["徐州", "豫州"], "议", "皖北，徐豫交界"),
    "亳州市": (["徐州", "豫州"], "议", "皖北，徐豫交界"),
    "阜阳市": (["徐州", "豫州"], "议", "皖北，徐豫交界"),
    "蚌埠市": (["徐州", "扬州"], "议", "皖中偏北，徐扬交界"),
    # 河北
    "唐山市": (["冀州", "幽州"], "议", "禹贡属冀；周礼幽州"),
    "保定市": (["冀州", "幽州"], "议", "禹贡属冀；周礼幽州"),
    "廊坊市": (["冀州", "幽州"], "议", "禹贡属冀；周礼幽州"),
    "秦皇岛市": (["冀州", "幽州"], "议", "禹贡属冀；周礼幽州"),
    "张家口市": (["冀州", "幽州"], "议", "禹贡属冀；周礼幽州"),
    "承德市": (["冀州", "幽州"], "议", "禹贡属冀；周礼幽州"),
    # 内蒙东部（九州外）
    "赤峰市": ([], "外", "内蒙东部，九州之外"),
    "通辽市": ([], "外", "内蒙东部，九州之外"),
    "呼伦贝尔市": ([], "外", "内蒙东北，九州之外"),
    "兴安盟": ([], "外", "内蒙东部，九州之外"),
    "锡林郭勒盟": ([], "外", "内蒙东部，九州之外"),
    # 陕西南部
    "汉中市": (["雍州", "梁州"], "议", "陕南，雍梁交界"),
    "安康市": (["雍州", "梁州"], "议", "陕南，雍梁交界"),
    "商洛市": (["雍州", "梁州"], "议", "陕南，雍梁交界"),
}


# 台湾县市：DataV 无下级数据，人工补。坐标为县市政府驻地近似值。
# (键名, 全名, 纬度, 经度, 层级)  键名即城市库里查的写法；新竹/嘉义市县同名，保留「市/县」后缀区分。
TAIWAN = [
    ("台北", "台北市", 25.0330, 121.5654, "county"),
    ("新北", "新北市", 25.0119, 121.4618, "county"),
    ("桃园", "桃园市", 24.9936, 121.3010, "county"),
    ("台中", "台中市", 24.1477, 120.6736, "county"),
    ("台南", "台南市", 22.9999, 120.2270, "county"),
    ("高雄", "高雄市", 22.6273, 120.3014, "county"),
    ("基隆", "基隆市", 25.1276, 121.7392, "county"),
    ("新竹市", "新竹市", 24.8138, 120.9675, "county"),
    ("新竹县", "新竹县", 24.8387, 121.0177, "county"),
    ("苗栗", "苗栗县", 24.5602, 120.8214, "county"),
    ("彰化", "彰化县", 24.0759, 120.5440, "county"),
    ("南投", "南投县", 23.9099, 120.6839, "county"),
    ("云林", "云林县", 23.7092, 120.4313, "county"),
    ("嘉义市", "嘉义市", 23.4801, 120.4491, "county"),
    ("嘉义县", "嘉义县", 23.4592, 120.3329, "county"),
    ("屏东", "屏东县", 22.6761, 120.4942, "county"),
    ("宜兰", "宜兰县", 24.7570, 121.7530, "county"),
    ("花莲", "花莲县", 23.9769, 121.6015, "county"),
    ("台东", "台东县", 22.7583, 121.1444, "county"),
    ("澎湖", "澎湖县", 23.5711, 119.5793, "county"),
    ("金门", "金门县", 24.4367, 118.3171, "county"),
    ("连江", "连江县", 26.1605, 119.9515, "county"),
]


def rule_for(rec):
    city = rec.get("city") or ""
    if city and city in CITY_EXC:
        return CITY_EXC[city]
    if rec["level"] == "city" and rec["name"] in CITY_EXC:
        return CITY_EXC[rec["name"]]
    prov = rec.get("province") or ""
    if prov in PROV:
        return PROV[prov]
    return ([], "外", "未归类")


def main():
    areas = [a for a in json.load(io.open(AREAS, encoding="utf-8"))
             if a.get("name") and a.get("center")]
    print("有效记录", len(areas))

    # ---- 旧数据（人工核定） ----
    old_cities = json.load(io.open(CITY_FILE, encoding="utf-8"))
    old_zhou = json.load(io.open(ZHOU_FILE, encoding="utf-8"))
    curated = {k: v for k, v in old_zhou["城市"].items()}
    print("人工核定 %d 座" % len(curated))

    # ---- 生成键 ----
    recs = []
    prov_center = {}
    for a in areas:
        if a["level"] == "province":
            prov_center[a["name"]] = a["center"]
            continue  # 省本身默认不作为目的地，直辖市/特区另行补
        lng, lat = a["center"][0], a["center"][1]
        recs.append({
            "adcode": a["adcode"],
            "name": a["name"],
            "base": short(a["name"]),
            "level": a["level"],
            "province": a["province"],
            "city": a["city"],
            "lat": round(lat, 4),
            "lon": round(lng, 4),
        })

    # 台湾县市（数据源无下级，人工补）
    for tkey, tname, tlat, tlon, tlv in TAIWAN:
        recs.append({
            "adcode": "TW-" + tkey, "name": tname, "base": tkey,
            "level": tlv, "province": "台湾省", "city": "",
            "lat": tlat, "lon": tlon,
        })

    for pname, (zl, grade, note) in [
        ("北京市", (["冀州", "幽州"], "议", "禹贡属冀；周礼职方氏为幽州")),
        ("天津市", (["冀州", "幽州"], "议", "禹贡属冀；周礼职方氏为幽州")),
        ("上海市", (["扬州"], "定", "")),
        ("重庆市", (["梁州"], "定", "")),
        ("香港特别行政区", (["扬州"], "定", "古属扬州刺史部南海郡")),
        ("澳门特别行政区", (["扬州"], "定", "古属扬州刺史部南海郡")),
    ]:
        c = prov_center.get(pname)
        if not c:
            continue
        recs.append({
            "adcode": pname, "name": pname, "base": short(pname),
            "level": "city", "province": pname, "city": "",
            "lat": round(c[1], 4), "lon": round(c[0], 4),
        })

    base_groups = defaultdict(list)
    for r in recs:
        base_groups[r["base"]].append(r)

    keyed = {}
    ambiguous = defaultdict(list)
    for b, group in base_groups.items():
        if len(group) == 1:
            keyed[b] = group[0]
            continue
        # 重名：市优先占用本名（西安市 vs 牡丹江西安区 → 西安 / 牡丹江西安）；
        # 同层重名（四处鼓楼区、闽台两个连江县）一律加前缀，基础名留给查询时提示歧义
        cities = [r for r in group if r["level"] == "city"]
        winner = cities[0] if len(cities) == 1 else None
        for r in group:
            if r is winner:
                k = b
            else:
                parent = short(r["city"] or r["province"])
                if parent and parent != b:
                    k = parent + b
                else:
                    k = r["name"] if r["name"] != b else b + "本级"
                if k in keyed:
                    k = b + "(" + r["name"] + ")"
                if k in keyed:
                    k = b + str(r["adcode"])
            keyed[k] = r
        ambiguous[b] = [k for k, r in keyed.items() if r["base"] == b]

    print("唯一键 %d，歧义名 %d 组" % (len(keyed), len(ambiguous)))

    # 人工核定键名与新键名对齐（旧「新竹」→ 新「新竹市」；新竹县不继承）
    for old_k, new_k in {"新竹": "新竹市"}.items():
        if old_k in curated and new_k in keyed and new_k not in curated:
            curated[new_k] = curated[old_k]

    # 补齐：人工核定但 DataV 未覆盖的
    old_cn = old_cities["中国"]
    bases = set(r["base"] for r in keyed.values()) | set(short(r["base"]) for r in keyed.values())
    appended = []
    for k in curated:
        if k in keyed or k in old_cities["海外"] or k in bases:
            continue
        if k in old_cn:
            lat, lon = old_cn[k]
            prov = "台湾省" if k in {"台北", "高雄", "台中", "台南", "新竹", "桃园"} else ""
            keyed[k] = {
                "adcode": "", "name": k, "base": k, "level": "city",
                "province": prov, "city": "", "lat": lat, "lon": lon,
            }
            appended.append(k)
    if appended:
        print("补齐人工核定（DataV 未覆盖）：", appended)

    # ---- 组装 ----
    cn = {}
    zhou_city = {}
    alias = {}
    for k, r in keyed.items():
        cn[k] = [r["lat"], r["lon"]]
        zl, grade, note = rule_for(r)
        if k in curated:
            entry = dict(curated[k])
            entry["源"] = "人工核定"
        else:
            entry = {"州": zl, "档": grade, "源": "批量推演"}
            if note:
                entry["注"] = note
        entry["全名"] = r["name"]
        entry["级"] = r["level"]
        entry["省"] = r["province"]
        if r["city"]:
            entry["市"] = r["city"]
        zhou_city[k] = entry
        # 别名：全名、省+市+全名、市+全名、省+全名，以及各自的去后缀写法
        alias[r["name"]] = k
        if r["city"]:
            alias[r["city"] + r["name"]] = k
            alias[r["province"] + r["city"] + r["name"]] = k
            alias[r["city"] + r["base"]] = k
            alias[r["province"] + r["city"] + r["base"]] = k
        alias[r["province"] + r["name"]] = k
        alias[r["province"] + r["base"]] = k
        parent = short(r["city"] or r["province"])
        if parent:
            alias[parent + r["base"]] = k

    # 台湾 22 县市统一注：旧注是「同上，两说并列」这类互指写法，逐城读会失效，改为自足表述
    TW_NOTE = "九州之外岛屿。《禹贡》不及；一说古属扬州徼外。两说并列，不作甲级依据。"
    for k, v in zhou_city.items():
        if v.get("省") == "台湾省":
            v["州"] = ["扬州"]
            v["档"] = "议"
            v["注"] = TW_NOTE

    # 海外沿用
    overseas = old_cities["海外"]
    for k in overseas:
        if k in curated:
            zhou_city[k] = dict(curated[k])
            zhou_city[k]["源"] = "人工核定"
            zhou_city[k]["级"] = "overseas"

    out_cities = {
        "_meta": {
            "说明": "城市经纬度参考库（WGS84 近似值，取行政区中心点）。精度约 0.01-0.05 度，用于 45 度方位扇区判定足够。",
            "用法": "城市名可写简称（上海、朝阳）；重名区县会以「市名+区名」消歧（如 北京朝阳、南通通州）。歧义名会提示候选。",
            "版本": "V2.0（2026-10），中国 %d + 海外 %d = %d 条，覆盖全国地级市与县级行政区" % (
                len(cn), len(overseas), len(cn) + len(overseas)),
            "数据来源": "阿里云 DataV.GeoAtlas areas_v3（2026-10 抓取），行政区划以国家统计局为准；坐标为行政区中心点，非市政府驻地。",
            "坐标性质": "center 为行政区几何中心附近，用于方位判定；若需精确到市政府驻地，请自行替换。",
            "重名处理": "同名区县加前缀消歧；基础名同时登记在 _ambiguous，查询时会提示候选而不是静默取一个。",
        },
        "中国": cn,
        "海外": overseas,
        "_alias": alias,
        "_ambiguous": {k: v for k, v in ambiguous.items()},
    }

    out_zhou = {
        "_meta": old_zhou["_meta"],
        "州五行": old_zhou["州五行"],
        "州出处": old_zhou["州出处"],
        "城市": zhou_city,
    }
    out_zhou["_meta"] = dict(old_zhou["_meta"])
    out_zhou["_meta"]["版本"] = "V2.0（2026-10）全国 %d 条，人工核定 %d / 批量推演 %d" % (
        len(zhou_city), sum(1 for v in zhou_city.values() if v.get("源") == "人工核定"),
        sum(1 for v in zhou_city.values() if v.get("源") == "批量推演"))
    out_zhou["_meta"]["批量推演说明"] = (
        "标「批量推演」的条目，州归属按「省规则 + 市例外 + 区县继承所属市」推导，"
        "属乙级推演，未经逐县考证。报告引用时必须说明这一点，不得当作甲级依据。"
    )

    json.dump(out_cities, io.open(CITY_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(out_zhou, io.open(ZHOU_FILE, "w", encoding="utf-8"), ensure_ascii=False)

    print("写出：中国 %d，海外 %d，合计 %d" % (len(cn), len(overseas), len(cn) + len(overseas)))
    print("档位", dict(Counter(v["档"] for v in zhou_city.values())))
    print("来源", dict(Counter(v.get("源") for v in zhou_city.values())))
    print("省覆盖", len(set(r["province"] for r in recs)))
    print("样例：", list(cn.items())[:3])
    for t in ["北京", "上海", "昆山", "北京朝阳", "南通通州", "鼓楼"]:
        print("  查", t, "->", cn.get(t), zhou_city.get(t, {}).get("州"))


if __name__ == "__main__":
    main()
