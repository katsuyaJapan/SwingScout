#!/usr/bin/env python3
import concurrent.futures, datetime, json, math, re, subprocess, tempfile, urllib.parse, urllib.request, xlrd, openpyxl
from pathlib import Path
from zoneinfo import ZoneInfo
from rights_sources import fetch_yahoo_rights
from volume_signals import analyze_volume_supply_demand

ROOT=Path(__file__).resolve().parents[1]
POST_EARNINGS_SAFE_DAYS=45
raw=json.loads((ROOT/"public/data/jpx-snapshot.json").read_text())
sector_proxy=json.loads((ROOT/"public/data/sector-data.json").read_text())
with tempfile.NamedTemporaryFile(suffix='.xls') as f:
  f.write(urllib.request.urlopen('https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls',timeout=30).read()); f.flush()
  sheet=xlrd.open_workbook(f.name).sheet_by_index(0); headers=[str(sheet.cell_value(0,i)).strip() for i in range(sheet.ncols)]
  ci=headers.index('コード'); si=headers.index('33業種区分'); mi=headers.index('市場・商品区分')
  master={str(sheet.cell_value(r,ci)).split('.')[0].zfill(4):(str(sheet.cell_value(r,si)).strip(),str(sheet.cell_value(r,mi)).strip()) for r in range(1,sheet.nrows)}
earnings={}; earnings_status={}; earnings_period={}; earnings_failures=[]; earnings_rows=0
earnings_index='https://www.jpx.co.jp/listing/event-schedules/financial-announcement/index.html'
earnings_page=urllib.request.urlopen(earnings_index,timeout=30).read().decode('utf-8','replace')
earnings_urls=sorted({urllib.parse.urljoin(earnings_index,path) for path in re.findall(r'href="([^"]+\.xlsx(?:\?[^\"]*)?)"',earnings_page,re.I)})
if not earnings_urls: raise RuntimeError('JPX決算予定表のリンクを取得できませんでした')
for url in earnings_urls:
  try:
    with tempfile.NamedTemporaryFile(suffix='.xlsx') as f:
      f.write(urllib.request.urlopen(url,timeout=30).read()); f.flush(); sh=openpyxl.load_workbook(f.name,data_only=True).active
      for row in sh.iter_rows(min_row=6,values_only=True):
        if not row[0] or not row[1]: continue
        earnings_rows+=1; code=str(row[1]).split('.')[0].zfill(4); raw_date=str(row[0]).strip()
        earnings_period[code]=str(row[7]).strip() if len(row)>7 and row[7] else None
        if '未定' in raw_date or 'undecided' in raw_date.lower():
          if code not in earnings: earnings_status[code]='UNDECIDED'
          continue
        date=row[0].strftime('%Y%m%d') if hasattr(row[0],'strftime') else raw_date.replace('/','').replace('-','')[:8]
        if re.fullmatch(r'\d{8}',date) and date>=raw['asOf']:
          if code not in earnings or date<earnings[code]: earnings[code]=date
          earnings_status[code]='CONFIRMED'
  except Exception as exc: earnings_failures.append(f'{url.rsplit("/",1)[-1]}: {exc}')
if earnings_rows<100 or len(earnings_failures)==len(earnings_urls):
  raise RuntimeError(f'JPX決算予定表の検証に失敗しました rows={earnings_rows}, failures={earnings_failures}')
rights={}; rights_rows=0; rights_row_errors=[]
rights_page=urllib.request.urlopen('https://www.jpx.co.jp/listing/others/ex-rights/',timeout=30).read().decode('utf-8','replace')
rights_match=re.search(r'href="([^"]+/\d{8}\.xls)"',rights_page)
if not rights_match: raise RuntimeError('JPX権利落ち予定ファイルのリンクを取得できませんでした')
rights_path=rights_match.group(1)
with tempfile.NamedTemporaryFile(suffix='.xls') as f:
  f.write(urllib.request.urlopen('https://www.jpx.co.jp'+rights_path,timeout=30).read()); f.flush()
  book=xlrd.open_workbook(f.name); sheet=book.sheet_by_index(0)
  for row in range(4,sheet.nrows):
    try:
      code=str(int(float(sheet.cell_value(row,4)))).zfill(4)
      record=xlrd.xldate_as_datetime(sheet.cell_value(row,0),book.datemode).date()
      ex_date=xlrd.xldate_as_datetime(sheet.cell_value(row,2),book.datemode).date()
      exit_day=ex_date-datetime.timedelta(days=1)
      while exit_day.weekday()>=5: exit_day-=datetime.timedelta(days=1)
      rights[code]={"rightsRecordDate":record.strftime('%Y%m%d'),"exRightsDate":ex_date.strftime('%Y%m%d'),"rightsExitDeadline":exit_day.strftime('%Y%m%d'),"rightsReason":str(sheet.cell_value(row,7)).strip() or "配当・権利","rightsSources":[{"name":"JPX","date":ex_date.strftime('%Y%m%d')}],"rightsCheckedSources":["JPX"]}
      rights_rows+=1
    except Exception as exc: rights_row_errors.append(f'row {row}: {exc}')
if rights_rows<1: raise RuntimeError(f'JPX権利落ち予定表の検証に失敗しました rows={rights_rows}, errors={rights_row_errors[:3]}')
def avg(xs): return sum(xs)/len(xs) if xs else 0
def rsi(xs,n=14):
  w=xs[-(n+1):]; gains=sum(max(0,w[i]-w[i-1]) for i in range(1,len(w))); losses=sum(max(0,w[i-1]-w[i]) for i in range(1,len(w)))
  return 100 if losses==0 else 100-(100/(1+gains/losses))
def triangle(value, center, half_width, maximum): return max(0.0, maximum*(1-abs(value-center)/half_width))
universe=[]; history=0; liquid=0
for s in raw["securities"]:
  aligned=[row for row in zip(s["c"],s["v"],s["t"],s.get("o",[None]*len(s["c"])),s.get("h",[None]*len(s["c"])),s.get("l",[None]*len(s["c"]))) if row[0] is not None and row[1] is not None and row[2] is not None][-250:]
  c=[row[0] for row in aligned]; v=[row[1] for row in aligned]; t=[row[2] for row in aligned]; o=[row[3] for row in aligned]; h=[row[4] for row in aligned]; l=[row[5] for row in aligned]
  if len(c)<200 or len(v)<20 or len(t)<20: continue
  history+=1; turnover20=t[-20:]; at=avg(turnover20); active_days=sum(value>=100_000_000 for value in turnover20)
  if at<300_000_000 or active_days<15: continue
  sector,market=master.get(s['code'],('その他製品','未分類'))
  if 'ETF' in market or 'REIT' in market or 'ファンド' in market: continue
  liquid+=1; close=c[-1]; ma5=avg(c[-5:]); ma25=avg(c[-25:]); ma75=avg(c[-75:]); high20=max(c[-20:]); rs=rsi(c); ret5=(close/c[-6]-1)*100; ret20=(close/c[-21]-1)*100; d25=(close/ma25-1)*100; vr=avg(v[-5:])/avg(v[-20:]); low10=min(c[-10:]); volume=analyze_volume_supply_demand(c,v,h,l,ma25)
  universe.append({'code':s['code'],'name':s['name'],'sector':sector,'close':close,'c':c,'v':v,'t':t,'o':o,'h':h,'l':l,'ma5':ma5,'ma25':ma25,'ma75':ma75,'high20':high20,'rsi':rs,'ret5':ret5,'ret20':ret20,'d25':d25,'vr':vr,'low':low10,'at':at,'activeDays':active_days,**volume})
sector_groups={}
for x in universe: sector_groups.setdefault(x['sector'],[]).append(x)
sectors=[]
for name,xs in sector_groups.items():
  r5=avg([x['ret5'] for x in xs]); r20=avg([x['ret20'] for x in xs]); breadth=100*sum(x['close']>x['ma25'] for x in xs)/len(xs); prior=100*sum(x['c'][-6]>avg(x['c'][-30:-5]) for x in xs)/len(xs); turn=avg([avg(x['t'][-5:])/avg(x['t'][-20:]) for x in xs]); acceleration=r5-r20/4
  raw_score=45+acceleration*3+(breadth-prior)*.35+(turn-1)*15-max(0,r5-4)*2; sample_factor=min(1,len(xs)/12); score=max(0,min(100,50+(raw_score-50)*sample_factor)); phase='資金流入開始' if len(xs)>=5 and turn>=1.05 and breadth>prior and r5>0 else ('次の流入候補' if len(xs)>=5 and (breadth>prior or acceleration>0) else '様子見')
  sectors.append({'name':name,'score':round(score),'phase':phase,'return5':round(r5,2),'return20':round(r20,2),'breadth':round(breadth,1),'breadthChange':round(breadth-prior,1),'turnoverRatio':round(turn,2),'stocks':len(xs)})
sectors.sort(key=lambda x:x['score'],reverse=True); sector_score={x['name']:x for x in sectors}
proxy_by_name={x['name']:x for x in sector_proxy.get('sectors',[])}
outflows=[]
for sector in sectors:
  prices=[x['close'] for x in proxy_by_name.get(sector['name'],{}).get('prices',[]) if x.get('close') is not None]
  if len(prices)<21: continue
  ret1=(prices[-1]/prices[-2]-1)*100; ret5=(prices[-1]/prices[-6]-1)*100; ret20=(prices[-1]/prices[-21]-1)*100
  slowdown=max(0,ret20/4-ret5); breadth_drop=max(0,-sector['breadthChange'])
  outflow_score=min(100,min(18,max(0,-ret1)*10)+min(28,max(0,-ret5)*8)+min(18,slowdown*4)+min(18,breadth_drop*.6)+(8 if sector['turnoverRatio']>=1.05 and ret5<0 else 0)+(min(10,max(0,ret20)*.8) if ret1<0 else 0))
  rounded_score=round(outflow_score)
  level='流出強め' if rounded_score>=60 else ('流出開始' if rounded_score>=45 else '弱含み警戒')
  action='新規停止・利益保護' if rounded_score>=60 else ('逆指値引き上げ' if rounded_score>=45 else '保有を重点監視')
  reasons=[]
  if ret1<0: reasons.append(f'1日 {ret1:.1f}%')
  if ret5<0: reasons.append(f'5日 {ret5:.1f}%')
  if breadth_drop>0: reasons.append(f'広がり {sector["breadthChange"]:.1f}pt')
  if slowdown>0: reasons.append('上昇モメンタム失速')
  outflows.append({'name':sector['name'],'score':rounded_score,'level':level,'action':action,'return1':round(ret1,2),'return5':round(ret5,2),'return20':round(ret20,2),'breadthChange':sector['breadthChange'],'turnoverRatio':sector['turnoverRatio'],'reasons':reasons[:3]})
outflows.sort(key=lambda x:x['score'],reverse=True)
rows=[]; excluded=[]
for x in universe:
  sec=sector_score[x['sector']]; reasons=[]
  deviation_score=triangle(x['d25'],1.5,5.0,17.0); rsi_score=triangle(x['rsi'],51.0,17.0,15.0); volume_score=x['volumeScore']; close_location_score=x['closeLocationScore']
  headroom=(x['high20']/x['close']-1)*100; headroom_score=triangle(headroom,6.0,7.0,9.0); trend_score=max(0,min(6,3+(x['ma5']/x['ma25']-1)*100*1.5))
  risk_width=max(0,(x['close']/x['low']-1)*100); risk_score=max(0,6-abs(risk_width-4)*1.2); liquidity_score=max(0,min(8,2+math.log10(max(x['at'],1)/100_000_000)*3))
  individual=deviation_score+rsi_score+volume_score+close_location_score+headroom_score+trend_score+risk_score+liquidity_score
  penalty=max(0,x['ret5']-5)*2.5+max(0,x['d25']-6)*3+(12 if x['rsi']>70 else 0)+(8 if x['close']>=x['high20'] and x['ret5']>5 else 0)
  score=max(0,min(100,sec['score']*.30+individual-penalty));
  if deviation_score>=12: reasons.append(f"25日線乖離 {x['d25']:+.1f}%")
  if rsi_score>=10: reasons.append(f"RSI {x['rsi']:.0f}で過熱前")
  if x['volumeSignal']=='GREEN': reasons.append(x['volumeSupplyDemand'])
  if headroom_score>=5: reasons.append(f"20日高値まで {headroom:.1f}%")
  earnings_flag=[] if x['code'] in earnings else (["EARNINGS_DATE_UNDECIDED"] if earnings_status.get(x['code'])=='UNDECIDED' else ["EARNINGS_UNCONFIRMED"])
  item={"code":x['code'],"name":x['name'],"sector":x['sector'],"sectorPhase":sec['phase'],"sectorScore":sec['score'],"close":x['close'],"score":round(score,3),"displayScore":round(score),"technical":round(individual,3),"liquidity":round(liquidity_score,3),"relativeVolume":x['relativeVolume'],"volumeSignal":x['volumeSignal'],"volumePhase":x['volumePhase'],"volumeSupplyDemand":x['volumeSupplyDemand'],"closeLocation":x['closeLocation'],"scoreBreakdown":{"sector":round(sec['score']*.30,2),"deviation":round(deviation_score,2),"rsi":round(rsi_score,2),"volume":round(volume_score,2),"closeLocation":round(close_location_score,2),"headroom":round(headroom_score,2),"trend":round(trend_score,2),"risk":round(risk_score,2),"liquidity":round(liquidity_score,2),"penalty":round(penalty,2)},"setup":"初動候補" if x['volumePhase'] in ('DRY_UP_REACCELERATION','BUYING_DEMAND','EARLY_ACCUMULATION') else "先回り候補","entry":f"{round(min(x['close'],x['ma5'])):,}円付近まで","invalidation":f"{round(x['low']):,}円割れ","reasons":reasons[:3],"riskFlags":earnings_flag,"earningsDate":earnings.get(x['code']),"earningsStatus":earnings_status.get(x['code'],'UNCONFIRMED'),"earningsPeriod":earnings_period.get(x['code']),"earningsDays":None,**rights.get(x['code'],{}),"metrics":{"closes":x['c'][-76:],"volumes":x['v'][-21:],"highs":x['h'][-21:],"lows":x['l'][-21:],"avgTurnover":x['at'],"activeTurnoverDays":x['activeDays']},"checks":{"price":True,"history":True,"liquidity":True,"fundamental":False,"earningsDate":x['code'] in earnings,"disclosure":False}}
  if penalty>=15: excluded.append({**item,'excludeReason':'5日上昇・25日線乖離・過熱のいずれか'})
  elif individual>=35 and sec['score']>=50: rows.append(item)
rows.sort(key=lambda x:x['score'],reverse=True); excluded.sort(key=lambda x:x['score'],reverse=True)
def secondary_earnings(row):
  code=row['code']; found=[]; reported=[]; checked=[]; errors=[]
  sources=[
    ('Yahoo!ファイナンス',f'https://finance.yahoo.co.jp/quote/{code}.T',r'(?:次回|直近)の決算発表日は(\d{4})年(\d{1,2})月(\d{1,2})日'),
    ('株予報',f'https://kabuyoho.jp/sp/report?bcode={code}',r'(?:発表済|決算発表予定)[^<]{0,40}?(\d{4})/(\d{1,2})/(\d{1,2})'),
  ]
  for name,url,pattern in sources:
    try:
      request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 SwingScout/1.4'})
      page=urllib.request.urlopen(request,timeout=20).read().decode('utf-8','replace'); checked.append(name)
      for y,m,d in set(re.findall(pattern,page)):
        date=f'{int(y):04d}{int(m):02d}{int(d):02d}'
        if date>=raw['asOf']: found.append({'name':name,'date':date})
        else: reported.append({'name':name,'date':date})
    except Exception as exc: errors.append(f'{name}: {exc}')
  return code,{'dates':found,'reported':reported,'checked':checked,'errors':errors}
def secondary_rights(row):
  return row['code'],fetch_yahoo_rights(row['code'],raw['asOf'])
def quote(row):
  try:
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{row["code"]}.T?range=5d&interval=1d'
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 SwingScout/1.3'})
    with urllib.request.urlopen(request,timeout=20) as response: chart=json.load(response)['chart']['result'][0]
    timestamps=chart.get('timestamp') or []; values=chart['indicators']['quote'][0]; closes=values.get('close') or []; highs=values.get('high') or []; volumes=values.get('volume') or []
    if not timestamps or not closes or closes[-1] is None:return row["code"],None
    day=datetime.datetime.fromtimestamp(timestamps[-1],ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')
    return row["code"],{"date":day,"high":float(highs[-1] or closes[-1]),"close":float(closes[-1]),"volume":int(volumes[-1] or 0)}
  except Exception:return row["code"],None
representatives=[]; seen=set()
for row in rows:
  if row['sector'] not in seen: representatives.append(row); seen.add(row['sector'])
top=representatives[:15]
top_codes={x['code'] for x in top}
top += [x for x in rows if x['code'] not in top_codes][:30-len(top)]
top.sort(key=lambda x:x['score'],reverse=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: secondary=dict(ex.map(secondary_earnings,top))
secondary_coverage=sum(bool(result['checked']) for result in secondary.values())
secondary_future_dates=0; secondary_recently_reported=0
for row in top:
  jpx_date=row.get('earningsDate'); evidence=[]
  if jpx_date: evidence.append({'name':'JPX','date':jpx_date})
  elif row.get('earningsStatus')=='UNDECIDED': evidence.append({'name':'JPX','status':'UNDECIDED'})
  result=secondary.get(row['code'],{}); evidence.extend(result.get('dates',[])); dates=sorted({x['date'] for x in evidence if x.get('date')})
  recent_reported=max((x['date'] for x in result.get('reported',[])),default=None)
  recently_reported=bool(recent_reported and 0 <= (datetime.datetime.strptime(raw['asOf'],'%Y%m%d')-datetime.datetime.strptime(recent_reported,'%Y%m%d')).days <= POST_EARNINGS_SAFE_DAYS)
  row['earningsSources']=evidence; row['earningsCheckedSources']=['JPX',*result.get('checked',[])]; row['earningsSourceErrors']=result.get('errors',[])
  flags=[x for x in row['riskFlags'] if x not in ('EARNINGS_UNCONFIRMED','EARNINGS_DATE_UNDECIDED','EARNINGS_DATE_CONFLICT')]
  if dates:
    secondary_future_dates+=1
    row['earningsDate']=dates[0]; row['earningsStatus']='CONFIRMED_MULTI_SOURCE'; row['checks']['earningsDate']=True
    if len(dates)>1: flags.append('EARNINGS_DATE_CONFLICT')
  elif recently_reported:
    secondary_recently_reported+=1
    row['earningsDate']=None; row['earningsStatus']='RECENTLY_REPORTED'; row['lastEarningsDate']=recent_reported
  elif row.get('earningsStatus')=='UNDECIDED': flags.append('EARNINGS_DATE_UNDECIDED')
  else: flags.append('EARNINGS_UNCONFIRMED')
  row['riskFlags']=flags
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: secondary_rights_results=dict(ex.map(secondary_rights,top))
rights_secondary_coverage=sum('Yahoo!ファイナンス株主優待' in result.get('checked',[]) for result in secondary_rights_results.values())
rights_disclosure_coverage=sum('TDnet掲載一覧' in result.get('checked',[]) for result in secondary_rights_results.values())
rights_secondary_errors=[]
for row in top:
  result=secondary_rights_results.get(row['code'],{}); rights_secondary_errors.extend(result.get('errors',[]))
  checked=['JPX',*result.get('checked',[])]; evidence=list(row.get('rightsSources',[])); flags=list(row.get('riskFlags',[]))
  current_ex=row.get('exRightsDate'); yahoo_events=result.get('events',[])
  for event in yahoo_events:
    evidence.append({'name':'Yahoo!ファイナンス株主優待','date':event['exRightsDate']})
  if yahoo_events:
    nearest=yahoo_events[0]; yahoo_ex=nearest['exRightsDate']
    if current_ex and current_ex!=yahoo_ex and abs((datetime.datetime.strptime(current_ex,'%Y%m%d')-datetime.datetime.strptime(yahoo_ex,'%Y%m%d')).days)<=10:
      flags.append('RIGHTS_DATE_CONFLICT')
    if not current_ex or yahoo_ex<current_ex:
      row.update(nearest); row['rightsReason']='株主優待（Yahoo!ファイナンス照合）'; current_ex=yahoo_ex
    elif current_ex==yahoo_ex and '株主優待' not in row.get('rightsReason',''):
      row['rightsReason']=f"{row.get('rightsReason','配当・権利')}・株主優待"
  disclosures=result.get('disclosures',[])
  if disclosures:
    flags.append('RIGHTS_RECENT_DISCLOSURE')
    evidence.extend({'name':'TDnet','status':title} for title in disclosures)
  row['rightsSources']=evidence; row['rightsCheckedSources']=checked; row['rightsSourceErrors']=result.get('errors',[]); row['rightsStatus']='CONFIRMED' if current_ex else 'NO_NEAR_TERM_EVENT'; row['riskFlags']=list(dict.fromkeys(flags))
jst_now=datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
after_close=(jst_now.hour,jst_now.minute)>=(15,30)
if after_close:
  with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex: quotes=dict(ex.map(quote,top))
else:
  quotes={x['code']:None for x in top}
quote_dates=[q["date"] for q in quotes.values() if q]
quote_date_set=set(quote_dates)
quotes_complete=len(quotes)==len(top) and all(quotes.get(x['code']) for x in top) and len(quote_date_set)==1
supplemental_date=next(iter(quote_date_set)) if quotes_complete else raw["asOf"]
seed={"source":raw["source"],"asOf":raw["asOf"],"supplementalDate":supplemental_date,"supplementalComplete":quotes_complete,"supplementalQuotes":quotes,"listed":len(raw["securities"]),"latestCoverage":raw["quality"]["coverage"][-1],"historyReady":history,"liquid":liquid,"primary":len(rows),"files":raw["quality"]["files"],"failures":raw["quality"]["failures"],"earningsQuality":{"files":len(earnings_urls),"rows":earnings_rows,"confirmed":len(earnings),"undecided":sum(x=='UNDECIDED' for x in earnings_status.values()),"secondaryCoverage":secondary_coverage,"secondaryTotal":len(top),"secondaryResolved":secondary_future_dates+secondary_recently_reported,"secondaryFutureDates":secondary_future_dates,"secondaryRecentlyReported":secondary_recently_reported,"postEarningsSafeDays":POST_EARNINGS_SAFE_DAYS,"failures":earnings_failures},"rightsQuality":{"jpxRows":rights_rows,"jpxRowErrors":len(rights_row_errors),"secondaryCoverage":rights_secondary_coverage,"disclosureCoverage":rights_disclosure_coverage,"secondaryTotal":len(top),"failures":rights_secondary_errors},"sectorSignals":sectors[:10],"sectorOutflows":outflows[:10],"sectorOutflowAsOf":sector_proxy.get('asOf',raw["asOf"]),"technicalCandidates":top,"excludedExtended":excluded[:10]}
(ROOT/"public/data/analysis-seed.json").write_text(json.dumps(seed,ensure_ascii=False,separators=(",",":")))
print(json.dumps({"size":(ROOT/"public/data/analysis-seed.json").stat().st_size,"primary":len(rows),"top":len(top),"supplementalDate":seed["supplementalDate"],"quotes":sum(q is not None for q in quotes.values())}))
