#!/usr/bin/env python3
import concurrent.futures, json, re, subprocess, tempfile, urllib.request
from collections import defaultdict
from pathlib import Path
from jpx_daily_sources import discover_daily_links

BASE="https://www.jpx.co.jp"; ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"public"/"data"/"jpx-snapshot.json"
UA={"User-Agent":"SwingScout/1.0"}
def get(url):
  with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=60) as r:return r.read()
def text(url):
  with tempfile.TemporaryDirectory() as d:
    p=Path(d)/"a.pdf";t=Path(d)/"a.txt";p.write_bytes(get(url));subprocess.run(["pdftotext","-layout",p,t],check=True,timeout=120);return t.read_text("utf-8","replace")
def num(s):
  try:return float(s.replace(",",""))
  except:return None
def parse_day(s,url):
  day=re.search(r"(\d{8})\.pdf$",url).group(1);out=[]
  for line in s.splitlines():
    # 権利落ち日には、コードと売買単位の間に D などの権利区分記号が入る。
    # 例: ``1407 D 100 ウエストＨＤ ...``
    m=re.match(r"^([0-9][0-9A-Z]{3}[0-9]?)\s+(?:[A-Z]+\s+)?(\d+)\s+(.+)$",line.strip())
    if not m:continue
    tok=m.group(3).split();tail=[]
    while tok and re.match(r"^(?:-?[\d,.]+|－)$",tok[-1]):tail.append(tok.pop())
    a=[num(x) for x in reversed(tail[-13:])]
    if len(a)==13 and (a[7]or a[3]):
      opens=[x for x in (a[0],a[4]) if x is not None]; highs=[x for x in (a[1],a[5]) if x is not None]; lows=[x for x in (a[2],a[6]) if x is not None]
      out.append((day,m.group(1)," ".join(tok),opens[0] if opens else None,max(highs) if highs else None,min(lows) if lows else None,(a[7]or a[3]),round(a[11]*1000) if a[11] else None,round(a[12]*1000) if a[12] else None))
  return out
def load(pair):
  _,url=pair;return url,parse_day(text(url),url)
def main():
  publications=discover_daily_links()
  work=[("d",url) for _,url in publications]
  expected_dates=[day for day,_ in publications]
  print(json.dumps({"discovered":len(work),"first":expected_dates[0],"latest":expected_dates[-1]}),flush=True)
  db=defaultdict(dict);fails=[]
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    fs={ex.submit(load,w):w for w in work}
    for f in concurrent.futures.as_completed(fs):
      try:
        url,rows=f.result()
        if len(rows)<1000:raise ValueError(f"only {len(rows)} rows")
        if len({row[1] for row in rows}) != len(rows):
          raise ValueError(f"duplicate security codes in {url}")
        for day,code,name,open_,high,low,close,volume,turnover in rows:db[code][day]=(name,open_,high,low,close,volume,turnover)
        print("ok",url.rsplit('/',1)[-1],len(rows),flush=True)
      except Exception as e:fails.append({"file":fs[f][1].rsplit('/',1)[-1],"error":str(e)})
  dates=sorted({d for rows in db.values() for d in rows})
  if fails or dates != expected_dates:
    raise RuntimeError(f"JPX daily history incomplete: days={len(dates)}, expected={len(expected_dates)}, failures={fails}")
  sec=[]
  for code,rows in sorted(db.items()):
    last=rows[max(rows)]; empty=(None,)*7
    sec.append({"code":code,"name":last[0],"o":[rows.get(d,empty)[1] for d in dates],"h":[rows.get(d,empty)[2] for d in dates],"l":[rows.get(d,empty)[3] for d in dates],"c":[rows.get(d,empty)[4] for d in dates],"v":[rows.get(d,empty)[5] for d in dates],"t":[rows.get(d,empty)[6] for d in dates]})
  cov=[sum(x["c"][i] is not None for x in sec) for i in range(len(dates))]
  output=OUT.with_suffix(".json.tmp")
  output.write_text(json.dumps({"source":"JPX東京証券取引所日報","asOf":dates[-1],"dates":dates,"securities":sec,"quality":{"files":len(work),"failures":fails,"coverage":cov}},ensure_ascii=False,separators=(",",":")))
  output.replace(OUT)
  print(json.dumps({"codes":len(sec),"days":len(dates),"latest":cov[-1],"failures":len(fails)}))
if __name__=="__main__":main()
