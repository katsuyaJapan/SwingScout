#!/usr/bin/env python3
import concurrent.futures, json, re, subprocess, tempfile, urllib.request
from collections import defaultdict
from pathlib import Path

BASE="https://www.jpx.co.jp"; ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"public"/"data"/"jpx-snapshot.json"
UA={"User-Agent":"SwingScout/1.0"}
def get(url):
  with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=60) as r:return r.read()
def page(url):return get(url).decode("utf-8","replace")
def urls(html,pat):return sorted(set(BASE+x for x in re.findall(pat,html)))
def text(url):
  with tempfile.TemporaryDirectory() as d:
    p=Path(d)/"a.pdf";t=Path(d)/"a.txt";p.write_bytes(get(url));subprocess.run(["pdftotext","-layout",p,t],check=True,timeout=120);return t.read_text("utf-8","replace")
def num(s):
  try:return float(s.replace(",",""))
  except:return None
def parse_month(s):
  out=[]; pat=re.compile(r"^(\d{8})\s+(\d{4}[A-Z0-9])\s+(.+?)\s+普通株式\s+(.+)$")
  for line in s.splitlines():
    m=pat.match(line.strip())
    if not m:continue
    a=[num(x) for x in m.group(4).split()]
    if len(a)>=8 and (a[7]or a[3]):out.append((m.group(1),m.group(2)[:4],m.group(3).strip(),None,None,None,a[7]or a[3],None,None))
  return out
def parse_day(s,url):
  day=re.search(r"(\d{8})\.pdf$",url).group(1);out=[]
  for line in s.splitlines():
    # 権利落ち日には、コードと売買単位の間に D などの権利区分記号が入る。
    # 例: ``1407 D 100 ウエストＨＤ ...``
    m=re.match(r"^(\d{4}[A-Z0-9]?)\s+(?:[A-Z]+\s+)?(\d+)\s+(.+)$",line.strip())
    if not m:continue
    tok=m.group(3).split();tail=[]
    while tok and re.match(r"^(?:-?[\d,.]+|－)$",tok[-1]):tail.append(tok.pop())
    a=[num(x) for x in reversed(tail[-13:])]
    if len(a)==13 and (a[7]or a[3]):
      opens=[x for x in (a[0],a[4]) if x is not None]; highs=[x for x in (a[1],a[5]) if x is not None]; lows=[x for x in (a[2],a[6]) if x is not None]
      out.append((day,m.group(1)[:4]," ".join(tok),opens[0] if opens else None,max(highs) if highs else None,min(lows) if lows else None,(a[7]or a[3]),round(a[11]*1000) if a[11] else None,round(a[12]*1000) if a[12] else None))
  return out
def load(pair):
  kind,url=pair;return url,(parse_month(text(url)) if kind=="m" else parse_day(text(url),url))
def main():
  hist=page(BASE+"/markets/statistics-equities/daily/03.html")
  work=[("m",u) for u in urls(hist,r'href="([^\"]+/202508\.pdf)"')]
  for n in range(8,14):
    try:h=page(BASE+f"/markets/statistics-equities/daily/00-archives-{n:02d}.html")
    except:continue
    work += [("d",u) for u in urls(h,r'href="([^\"]+/stq_2025(?:09|10|11|12)\d{2}\.pdf)"')]
  for n in range(0,8):
    path="index.html" if n==0 else f"00-archives-{n:02d}.html"
    try:h=page(BASE+"/markets/statistics-equities/daily/"+path)
    except:continue
    work += [("d",u) for u in urls(h,r'href="([^\"]+/stq_2026\d{4}\.pdf)"')]
  work=list(dict.fromkeys(work));db=defaultdict(dict);fails=[]
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    fs={ex.submit(load,w):w for w in work}
    for f in concurrent.futures.as_completed(fs):
      try:
        url,rows=f.result()
        if len(rows)<1000:raise ValueError(f"only {len(rows)} rows")
        for day,code,name,open_,high,low,close,volume,turnover in rows:db[code][day]=(name,open_,high,low,close,volume,turnover)
        print("ok",url.rsplit('/',1)[-1],len(rows),flush=True)
      except Exception as e:fails.append({"file":fs[f][1].rsplit('/',1)[-1],"error":str(e)})
  dates=sorted({d for rows in db.values() for d in rows})[-250:];sec=[]
  for code,rows in sorted(db.items()):
    last=rows[max(rows)]; empty=(None,)*7
    sec.append({"code":code,"name":last[0],"o":[rows.get(d,empty)[1] for d in dates],"h":[rows.get(d,empty)[2] for d in dates],"l":[rows.get(d,empty)[3] for d in dates],"c":[rows.get(d,empty)[4] for d in dates],"v":[rows.get(d,empty)[5] for d in dates],"t":[rows.get(d,empty)[6] for d in dates]})
  cov=[sum(x["c"][i] is not None for x in sec) for i in range(len(dates))]
  OUT.write_text(json.dumps({"source":"JPX東京証券取引所日報","asOf":dates[-1],"dates":dates,"securities":sec,"quality":{"files":len(work),"failures":fails,"coverage":cov}},ensure_ascii=False,separators=(",",":")))
  print(json.dumps({"codes":len(sec),"days":len(dates),"latest":cov[-1],"failures":len(fails)}))
if __name__=="__main__":main()
