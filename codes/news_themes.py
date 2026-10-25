"""Systematic, transparent, replicable news-theme analysis (22-25 Oct 2026).
Method is printed with the results so it can be quoted verbatim."""
import json, urllib.request, time, collections, pathlib, re
KEY = open('/tmp/wfc8.txt').readline().strip()
URL = "https://newsapi.ai/api/v1/article/getArticles?apiKey=" + KEY
QUERIES = [{"keyword":"Tai Po fire"},{"keyword":"Wang Fuk Court"},{"keyword":"宏福苑"},
           {"keyword":"Tai Po fire report"},{"keyword":"宏福苑 報告"}]
WINDOW = ("2026-10-22", "2026-10-25")
THEMES = {
 "A. Report publication & redaction": ["report","redact","submit","release","publish","公布","提交","刪節","報告"],
 "B. Accountability & discipline":    ["accountab","disciplin","resign","apolog","問責","落台","道歉","紀律","究責"],
 "C. Reforms & legislation":          ["reform","legislat","ordinance","amend","改革","法例","修例","規管","條例"],
 "D. Which departments / ICU":        ["icu","fire services","buildings department","labour","department","bodies","部門","屋宇署","勞工處","消防處","機電"],
 "E. Residents, rehousing, money":    ["resident","rehous","compensat","grant","安置","賠償","居民","津貼","上樓"],
 "F. Contractors & building safety":  ["contractor","prestige","will power","netting","scaffold","foam","lift","承建商","棚網","裝修","升降機"],
 "G. Tender / bid-rigging":           ["tender","bid","collusion","rigging","投標","串標","圍標"],
 "H. Fire-service response & cause":  ["999","alarm","firefight","cause","cigarette","evacuat","警鐘","起火","疏散","消防"],
}
def fetch(q, n=50):
    body={"action":"getArticles","resultType":"articles","query":{"$query":q},
          "articlesCount":n,"articlesPage":1,"articlesSortBy":"date"}
    req=urllib.request.Request(URL,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=45) as r:
        return json.loads(r.read().decode()).get("articles",{}).get("results") or []
raw=[]
for q in QUERIES:
    for a in range(2):
        try:
            got=fetch(q); raw+=got; print("query %-28s -> %d" % (str(q), len(got))); break
        except Exception as e:
            print("retry", str(e)[:50]); time.sleep(3)
# dedup: exact title, then title-normalised
seen={}
for a in raw:
    t=re.sub(r"\s+"," ",(a.get("title") or "")).strip()
    d=(a.get("date") or "")[:10]
    if t and WINDOW[0] <= d <= WINDOW[1] and t not in seen:
        seen[t]={"title":t,"date":d,"source":((a.get("source") or {}).get("title") or "?"),
                 "url":a.get("url") or "","body":(a.get("body") or "").strip()}
arts=list(seen.values())
print("\nWINDOW %s..%s | raw=%d | unique after dedup=%d | with body>400: %d"
      % (WINDOW[0], WINDOW[1], len(raw), len(arts), sum(1 for a in arts if len(a["body"])>400)))
themes=collections.defaultdict(list)
for a in arts:
    blob=(a["title"]+" "+a["body"]).lower()
    for name,kws in THEMES.items():
        if any(k.lower() in blob for k in kws):
            themes[name].append(a)
print("\n=== THEMES (multi-label; an article can count in several) ===")
for name in sorted(THEMES):
    rows=sorted(themes.get(name,[]), key=lambda x:x["date"], reverse=True)
    print("\n%s — %d articles" % (name, len(rows)))
    for a in rows[:4]:
        print("   %s | %-22s | %s" % (a["date"], a["source"][:22], a["title"][:80]))
out=pathlib.Path("/Users/simonwang/Workspace/wangfukcourtfirereport/data/news_themes_20261025.json")
out.write_text(json.dumps({"window":WINDOW,"queries":[str(q) for q in QUERIES],
    "themes":{k:[{"date":a["date"],"source":a["source"],"title":a["title"],"url":a["url"]} for a in v]
              for k,v in themes.items()},
    "articles":arts}, ensure_ascii=False, indent=1))
print("\nsaved", out.name, out.stat().st_size, "bytes")
