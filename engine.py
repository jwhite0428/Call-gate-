"""Original BTC/USD 15-minute prediction research engine. Paper-only, no broker orders."""
import os, time, math, sqlite3, json, datetime as dt
from pathlib import Path
import requests

DB=Path(os.getenv('QG_DB',str(Path(__file__).with_name('quantgate.sqlite3'))))
API='https://api.exchange.coinbase.com'
KALSHI_API='https://external-api.kalshi.com/trade-api/v2'
HEADERS={'User-Agent':'BTC15-Reference-Style-Paper-Research/3.0','Accept':'application/json'}

def conn():
    c=sqlite3.connect(str(DB),timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE IF NOT EXISTS candles(ts INTEGER PRIMARY KEY, low REAL, high REAL, open REAL, close REAL, volume REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS signals(window INTEGER NOT NULL,layer TEXT NOT NULL,side TEXT NOT NULL,confidence REAL NOT NULL,signal_ts INTEGER NOT NULL,spot REAL NOT NULL,evidence TEXT NOT NULL,outcome TEXT,close_price REAL,closed_ts INTEGER,PRIMARY KEY(window,layer))')
    c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,val TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS decisions(window INTEGER PRIMARY KEY,side TEXT NOT NULL,reason TEXT NOT NULL,mode TEXT NOT NULL,price REAL,created_ts INTEGER NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS paper_trades(window INTEGER PRIMARY KEY,side TEXT NOT NULL,signal_price REAL NOT NULL,contracts INTEGER NOT NULL,entry_cost REAL NOT NULL,fee_per_contract REAL NOT NULL,assumed_entry_price REAL NOT NULL,created_ts INTEGER NOT NULL,status TEXT NOT NULL DEFAULT OPEN,result TEXT,settlement_price REAL,pnl REAL,closed_ts INTEGER)')
    # Safe upgrades: preserve all older hypothetical trades without relabeling them as quotes.
    cols={r[1] for r in c.execute('PRAGMA table_info(paper_trades)')}
    migrated=False
    for name,sql_type in [('entry_source','TEXT'),('market_ticker','TEXT'),('quote_ts','INTEGER'),('quote_side','TEXT'),('quote_available','REAL'),('settlement_source','TEXT')]:
        if name not in cols:
            c.execute(f'ALTER TABLE paper_trades ADD COLUMN {name} {sql_type}')
            migrated=True
    if migrated:c.execute("UPDATE paper_trades SET entry_source='LEGACY_ASSUMED' WHERE entry_source IS NULL")
    c.commit();return c

def setting(key,default):
    with conn() as c:r=c.execute('SELECT val FROM settings WHERE key=?',(key,)).fetchone()
    return r['val'] if r else str(default)
def set_setting(key,value):
    with conn() as c:c.execute('INSERT INTO settings(key,val) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET val=excluded.val',(key,str(value)))

def parse_candles(raw):
    if not isinstance(raw,list):raise ValueError('Unexpected candle response')
    return {int(x[0]):dict(ts=int(x[0]),low=float(x[1]),high=float(x[2]),open=float(x[3]),close=float(x[4]),volume=float(x[5])) for x in raw if isinstance(x,list) and len(x)>=6}

def store_candles(candles):
    with conn() as c:
        c.executemany('INSERT INTO candles(ts,low,high,open,close,volume) VALUES(:ts,:low,:high,:open,:close,:volume) ON CONFLICT(ts) DO UPDATE SET low=excluded.low,high=excluded.high,open=excluded.open,close=excluded.close,volume=excluded.volume',candles.values())

def historical_candles(hours=24):
    with conn() as c:rows=c.execute('SELECT * FROM candles WHERE ts>=? ORDER BY ts',(int(time.time())-hours*3600,)).fetchall()
    return {r['ts']:dict(r) for r in rows}

def bootstrap_history():
    # Historical backfill is public Coinbase data, not predictions or artificial performance.
    now=int(time.time())//60*60
    previous=int(setting('last_bootstrap',0))
    if now-previous<3600:return
    any_good=False
    for block in range(4):
        end=now-block*240*60;start=end-240*60
        params={'granularity':60,'start':dt.datetime.fromtimestamp(start,dt.timezone.utc).isoformat(),'end':dt.datetime.fromtimestamp(end,dt.timezone.utc).isoformat()}
        try:
            response=requests.get(f'{API}/products/BTC-USD/candles',params=params,headers=HEADERS,timeout=15);response.raise_for_status()
            data=parse_candles(response.json())
            if data:store_candles(data);any_good=True
        except Exception:continue
    if any_good:set_setting('last_bootstrap',now)

def feed():
    r=requests.get(f'{API}/products/BTC-USD/candles',params={'granularity':60},headers=HEADERS,timeout=12);r.raise_for_status()
    candles=parse_candles(r.json())
    if not candles:raise ValueError('No BTC minute candles received')
    store_candles(candles)
    r=requests.get(f'{API}/products/BTC-USD/ticker',headers=HEADERS,timeout=12);r.raise_for_status()
    price=float(r.json()['price'])
    return historical_candles(),price

def ema(xs,n):
    a=2/(n+1);v=xs[0]
    for x in xs[1:]:v=x*a+v*(1-a)
    return v

def readings(candles,window,minute):
    cutoff=window+minute*60
    history=[candles[t] for t in sorted(candles) if t+60<=cutoff]
    if len(history)<32 or any(t not in candles for t in range(window,cutoff,60)):return None
    xs=[x['close'] for x in history]
    e9,e20=ema(xs[-70:],9),ema(xs[-90:],20)
    changes=[xs[i]-xs[i-1] for i in range(1,len(xs))]
    up=sum(max(v,0) for v in changes[-14:]);down=sum(max(-v,0) for v in changes[-14:])
    rsi=100 if down==0 else 100-100/(1+up/down)
    move=(xs[-1]/xs[-5]-1)*100
    longer=(xs[-1]/xs[-11]-1)*100
    atr=sum(max(x['high']-x['low'],abs(x['high']-p['close']),abs(x['low']-p['close'])) for x,p in zip(history[-14:],history[-15:-1]))/14
    def vote(v,threshold=0):return 'UP' if v>threshold else 'DOWN' if v< -threshold else 'SKIP'
    return dict(trend=vote((e9/e20-1)*100,.003),momentum=vote(move,.015),rsi=vote(rsi-50,3),strength=vote(longer,.025),volatility=atr/xs[-1]*100,ema9=e9,ema20=e20,rsi_value=rsi,move=move,spot=xs[-1],window_open=candles[window]['open'])

def combine(votes):return votes[0] if votes and 'SKIP' not in votes and len(set(votes))==1 else 'SKIP'

def learning_samples(candles,current_window):
    samples=[]
    windows=sorted({t//900*900 for t in candles if t+900<=current_window})
    for w in windows:
        if all(w+i*60 in candles for i in [0,1,2,3,14]):
            start=candles[w]['open'];mid=candles[w+180]['close'];close=candles[w+840]['close']
            if start<=0:continue
            samples.append(((mid/start-1)*100,'UP' if close>start else 'DOWN' if close<start else 'TIE'))
    return samples

def evaluate(candles,window,minute,layer):
    r=readings(candles,window,minute)
    if r is None:return None
    if layer=='call':votes=[r['trend'],r['momentum']];labels=['Current rule','3-factor score']
    elif layer=='quant':votes=[r['trend'],r['rsi'],r['strength']];labels=['Reading 1','Reading 2','Final check']
    else:
        samples=learning_samples(candles,window)
        probe=(candles[window+180]['close']/candles[window]['open']-1)*100
        nearest=sorted(samples,key=lambda x:abs(x[0]-probe))[:25]
        applicable=[x[1] for x in nearest if x[1]!='TIE']
        p=sum(x=='UP' for x in applicable)/len(applicable) if applicable else .5
        side='UP' if len(samples)>=25 and p>=.57 else 'DOWN' if len(samples)>=25 and p<=.43 else 'SKIP'
        confidence=round(100*(p if side=='UP' else 1-p),1) if side!='SKIP' else 50.0
        evidence=json.dumps({'readings':['Nearest-window historical outcomes'],'samples':len(samples),'nearby_samples':len(applicable),'up_fraction':round(p,3),'source':'Coinbase BTC/USD spot','note':'Historical analogue prediction, not a proprietary ML model'})
        return side,confidence,evidence,r['spot']
    side=combine(votes)
    if r['volatility']<.012:side='SKIP'
    agree=sum(v==side for v in votes) if side!='SKIP' else 0
    confidence=round(min(88,50+agree*8+min(abs(r['move'])*65,8)),1) if side!='SKIP' else 50.
    evidence=json.dumps(dict(readings=votes,labels=labels,ema9=round(r['ema9'],2),ema20=round(r['ema20'],2),rsi=round(r['rsi_value'],1),momentum_pct=round(r['move'],3),source='Coinbase BTC/USD spot',note='Agreement' if side!='SKIP' else 'Disagreement or insufficient volatility'))
    return side,confidence,evidence,r['spot']

def process(candles,price,now=None):
    now=int(now if now is not None else time.time());window=now//900*900
    with conn() as c:
        for layer,minute in [('learning',4),('call',int(setting('call_minute',6))),('quant',int(setting('call_minute',6)))]:
            if now<window+minute*60:continue
            if c.execute('SELECT 1 FROM signals WHERE window=? AND layer=?',(window,layer)).fetchone():continue
            result=evaluate(candles,window,minute,layer)
            if result is None:continue
            side,conf,evidence,spot=result
            c.execute('INSERT OR IGNORE INTO signals(window,layer,side,confidence,signal_ts,spot,evidence) VALUES(?,?,?,?,?,?,?)',(window,layer,side,conf,window+minute*60,spot,evidence))
        for r in c.execute('SELECT window,layer,side FROM signals WHERE outcome IS NULL AND window<?',(window,)).fetchall():
            last=candles.get(r['window']+840);first=candles.get(r['window'])
            if not last or not first:continue
            truth='UP' if last['close']>first['open'] else 'DOWN' if last['close']<first['open'] else 'TIE'
            outcome='SKIP' if r['side']=='SKIP' or truth=='TIE' else ('WIN' if r['side']==truth else 'LOSS')
            c.execute('UPDATE signals SET outcome=?,close_price=?,closed_ts=? WHERE window=? AND layer=?',(outcome,last['close'],r['window']+900,r['window'],r['layer']))
    update_decision(window,now,price)
    settle_paper_trades(candles,window)
    return window

def update_decision(window,now,price):
    """Lock Call once; retry an eligible $10 PAPER quote within the 60s entry window.

    Critical: creating a decision is NOT the same as successfully recording a
    paper trade. Quote failures remain observable and are retried; skipped
    signal decisions and old windows are never turned into entries.
    """
    signal_due=window+int(setting('call_minute',6))*60
    with conn() as c:
        existing=c.execute('SELECT * FROM decisions WHERE window=?',(window,)).fetchone()
        if existing is None:
            cr=c.execute('SELECT * FROM signals WHERE window=? AND layer="call"',(window,)).fetchone()
            qr=c.execute('SELECT * FROM signals WHERE window=? AND layer="quant"',(window,)).fetchone()
            if not cr:return
            if setting('call_enabled','1')!='1':side='SKIP';why='Call switch off'
            elif cr['side']=='SKIP':side='SKIP';why='Call readings disagree or skip'
            elif setting('gate_enabled','1')=='1' and (not qr or qr['side']!=cr['side']):side='SKIP';why='Quant Gate did not agree'
            else:side=cr['side'];why='Call and enabled confirmation layers agree'
            mode=setting('call_mode','Display only')
            if side!='SKIP' and now>signal_due+60:side='SKIP';why='Missed timely paper entry window'
            if mode=='Display only':why+='; display only'
            elif mode=='Display, then confirm':why+='; confirmation required'
            elif side!='SKIP':why+='; hypothetical PAPER entry only'
            c.execute('INSERT OR IGNORE INTO decisions(window,side,reason,mode,price,created_ts) VALUES(?,?,?,?,?,?)',
                      (window,side,why,mode,price if side!='SKIP' and mode=='Place trades automatically' else None,now))
            existing=c.execute('SELECT * FROM decisions WHERE window=?',(window,)).fetchone()

        # The decision's original mode, side and timing remain locked. Do not
        # turn a display-only or skipped decision into a trade retroactively.
        if existing['side'] not in ('UP','DOWN') or existing['mode']!='Place trades automatically':return
        if c.execute('SELECT 1 FROM paper_trades WHERE window=?',(window,)).fetchone():return
        if not (signal_due<=now<=signal_due+60):
            if 'ENTRY WINDOW CLOSED' not in existing['reason']:
                c.execute('UPDATE decisions SET reason=reason||? WHERE window=?',
                          ('; ENTRY WINDOW CLOSED without a valid Kalshi ask',window))
            return

        try:
            quote=kalshi_entry_quote(window,now,existing['side'])
            if abs(quote['ts']-int(time.time()))>20:raise ValueError('Stale quote')
            stake=10.0  # HARD CAP including estimated fees
            fee=max(0.,min(.20,float(setting('paper_fee_cents','1'))/100))
            cost=quote['ask']
            contracts=min(math.floor(stake/(cost+fee)),quote['quantity'])
            if contracts<=0:raise ValueError('Insufficient top-of-book size / $10 budget')
            c.execute("""INSERT OR IGNORE INTO paper_trades
                (window,side,signal_price,contracts,entry_cost,fee_per_contract,
                 assumed_entry_price,created_ts,status,entry_source,market_ticker,
                 quote_ts,quote_side,quote_available)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (window,existing['side'],price,contracts,round(contracts*(cost+fee),4),fee,cost,
                 now,'OPEN',quote['source'],quote['ticker'],quote['ts'],quote['side'],quote['quantity']))
            c.execute('UPDATE decisions SET reason=? WHERE window=?',
                      ('PAPER entry recorded from '+quote['source']+'; NOT an executed fill',window))
        except (requests.RequestException,ValueError,KeyError,TypeError,IndexError) as exc:
            # Replace error each attempt, instead of appending an ever-growing string.
            msg='Kalshi quote unavailable; retrying within 60s: '+str(exc)[:200]
            c.execute('UPDATE decisions SET reason=? WHERE window=?',(msg,window))

def kalshi_get(path,params=None):
    r=requests.get(KALSHI_API+path,params=params,headers=HEADERS,timeout=9)
    r.raise_for_status()
    data=r.json()
    if not isinstance(data,dict):raise ValueError('Malformed Kalshi API response')
    return data

def _timestamp(v):
    if not v:return None
    try:return int(dt.datetime.fromisoformat(str(v).replace('Z','+00:00')).timestamp())
    except (TypeError,ValueError):return None

def kalshi_market(window,now):
    """Discover the unique currently tradable KXBTC15M market ending with this window.

    open_time is a LISTING timestamp, and may predate the 15-minute interval;
    do not require it to match the interval start. Never pick a nearby market.
    """
    params={'series_ticker':'KXBTC15M','status':'open','limit':200}
    candidates=[]
    pages=0
    while pages<5:
        data=kalshi_get('/markets',params)
        pages+=1
        for m in data.get('markets',[]):
            if m.get('status') not in ('active','open'):continue
            end=_timestamp(m.get('close_time'))
            ticker=str(m.get('ticker') or '')
            if (end is not None and abs(end-(window+900))<=5 and
                    ticker.startswith('KXBTC15M-')):
                candidates.append(m)
        cursor=data.get('cursor')
        if not cursor or candidates:break
        params['cursor']=cursor
    unique={m['ticker']:m for m in candidates}
    if len(unique)!=1:
        raise ValueError(f'Expected one active KXBTC15M market closing at '+
                         f'{dt.datetime.fromtimestamp(window+900,dt.timezone.utc).isoformat()}, '+
                         f'found {len(unique)} after {pages} page(s)')
    return next(iter(unique.values()))

def _book_levels(book,side):
    """Derive a YES/NO ask from the best opposite bid, with schema-safe units."""
    opposite='no' if side=='UP' else 'yes'
    # New Kalshi API: orderbook_fp with {yes_dollars,no_dollars}.
    # Older API: orderbook with the same fields or integer-cent yes/no.
    if isinstance(book.get('orderbook_fp'),dict):
        ob=book['orderbook_fp']
    else:
        ob=book.get('orderbook',book)
    if not isinstance(ob,dict):raise ValueError('Unexpected orderbook structure')
    dollar_key=opposite+'_dollars'
    if dollar_key in ob:
        raw=ob[dollar_key] or []
        cents=False
    else:
        raw=ob.get(opposite) or []
        cents=True
    levels=[]
    for row in raw:
        try:
            bid=float(row[0]);quantity=float(row[1])
            if cents:bid/=100.0
            ask=round(1-bid,4)
            if .01<=ask<=.99 and quantity>=1:levels.append((ask,math.floor(quantity)))
        except (TypeError,ValueError,IndexError,KeyError):continue
    return sorted(levels,key=lambda x:x[0])

def _market_ask(market,side):
    """Use exchange-published market ask and *published top ask size*, no guesses."""
    prefix='yes' if side=='UP' else 'no'
    raw=market.get(prefix+'_ask_dollars')
    size=market.get(prefix+'_ask_size_fp')
    try:
        ask=float(raw);qty=math.floor(float(size))
    except (TypeError,ValueError,OverflowError):
        raise ValueError('Published '+prefix.upper()+' ask or size unavailable')
    if not (.01<=ask<=.99 and qty>=1):
        raise ValueError('Published '+prefix.upper()+' ask/size not tradeable')
    return round(ask,4),qty

def kalshi_entry_quote(window,now,side):
    market=kalshi_market(window,now)
    ticker=market['ticker']
    book_error=None
    try:
        book=kalshi_get(f'/markets/{ticker}/orderbook',{'depth':0})
        levels=_book_levels(book,side)
        if levels:
            ask,qty=levels[0]
            return {'ticker':ticker,'ask':ask,'quantity':math.floor(qty),
                    'ts':int(time.time()),'side':'YES' if side=='UP' else 'NO',
                    'source':'KALSHI_LIVE_ASK'}
        book_error='empty opposite-side book'
    except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
        book_error=str(exc)[:90]
    # The market list may lag the book. Re-read the *single* market just before entry.
    current=kalshi_get('/markets/'+ticker).get('market',{})
    if not isinstance(current,dict) or current.get('ticker')!=ticker:
        raise ValueError('Fresh market details unavailable')
    if current.get('status') not in ('active','open'):
        raise ValueError('Market no longer open')
    try:
        ask,qty=_market_ask(current,side)
    except ValueError as exc:
        raise ValueError(f'Order book failed ({book_error}); market snapshot failed ({exc})')
    return {'ticker':ticker,'ask':ask,'quantity':qty,'ts':int(time.time()),
            'side':'YES' if side=='UP' else 'NO','source':'KALSHI_MARKET_ASK'}

def read_layer(layer,limit=100):
    with conn() as c:return [dict(r) for r in c.execute('SELECT * FROM signals WHERE layer=? ORDER BY window DESC LIMIT ?',(layer,limit))]
def read_decisions(limit=100):
    with conn() as c:return [dict(r) for r in c.execute('SELECT * FROM decisions ORDER BY window DESC LIMIT ?',(limit,))]

def window_stats(candles,now,price):
    window=now//900*900
    cur=candles.get(window)
    if not cur:return {}
    op=cur['open'];gap=price-op;remaining=max(0,window+900-now)
    completed=[(w,candles[w+840]['close']-candles[w]['open']) for w in sorted({t//900*900 for t in candles if t+900<=window}) if w in candles and w+840 in candles]
    recent=completed[-12:]
    ups=sum(delta>0 for _,delta in recent);downs=sum(delta<0 for _,delta in recent)
    latest=sorted(t for t in candles if t+60<=now)
    def price_at(seconds):
        t=now//60*60-seconds
        item=candles.get(t)
        return item['open'] if item else None
    past1=price_at(60);past5=price_at(300)
    abs15=[abs(x[1]) for x in completed[-48:]]
    typical=sum(abs15)/len(abs15) if abs15 else None
    byhour={}
    for w,delta in completed:
        hour=dt.datetime.fromtimestamp(w,dt.timezone.utc).hour
        byhour.setdefault(hour,[]).append(abs(delta))
    byhour={hour:round(sum(v)/len(v),2) for hour,v in byhour.items()}
    # Last 12 hours: aggregate actual completed 1m candles, not inferred prices.
    minmoves=[abs(x['close']-x['open']) for t,x in candles.items() if now-43200<=t<now-60]
    typical1=(sum(minmoves)/len(minmoves)) if minmoves else None
    needed=max(0,op-price)
    historic_stretches=[]
    for w,_ in completed[-96:]:
        if all(w+j*60 in candles for j in range(15)):
            historic_stretches.append((min(x['low'] for x in (candles[w+j*60] for j in range(15))),max(x['high'] for x in (candles[w+j*60] for j in range(15)))))
    return dict(window=window,window_open=op,price=price,gap=gap,remaining=remaining,ups=ups,downs=downs,completed=completed,typical=typical,typical1=typical1,byhour=byhour,past1=past1,past5=past5,needed=needed,per_min=needed/max(remaining/60,.01),history_count=len(completed),stretches=historic_stretches)


def settle_paper_trades(candles,latest_window):
    """Grade the paper ledger only after full interval closes. No fabricated fills."""
    with conn() as c:
        pending=c.execute("SELECT * FROM paper_trades WHERE status='OPEN' AND window<?",(latest_window,)).fetchall()
        for t in pending:
            if t['entry_source'] in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK'):
                # Pay out only using official contract outcome, not Coinbase direction.
                try:
                    market=kalshi_get('/markets/'+t['market_ticker']).get('market',{})
                except (requests.RequestException,ValueError,KeyError):continue
                outcome=str(market.get('result') or '').lower()
                if outcome not in ('yes','no'):continue
                win=(outcome=='yes' and t['side']=='UP') or (outcome=='no' and t['side']=='DOWN')
                result='WIN' if win else 'LOSS'
                pnl=(t['contracts'] if win else 0)-t['entry_cost']
                c.execute("UPDATE paper_trades SET status='CLOSED',result=?,pnl=?,closed_ts=?,settlement_source='KALSHI_MARKET_RESULT' WHERE window=? AND status='OPEN'",
                          (result,round(pnl,4),int(time.time()),t['window']))
                continue
            initial=candles.get(t['window']);final=candles.get(t['window']+840)
            if not initial or not final:continue
            start=float(initial['open']);end=float(final['close'])
            if end==start:
                # A spot tie has no direction; mark void and zero P&L (not a Kalshi settlement rule).
                result='VOID';pnl=0.
            else:
                outcome='UP' if end>start else 'DOWN'
                result='WIN' if outcome==t['side'] else 'LOSS'
                # Each winner pays an assumed $1.00 per contract. An entry fee is included in entry_cost.
                pnl=(t['contracts'] if result=='WIN' else 0)-t['entry_cost']
            c.execute("UPDATE paper_trades SET status='CLOSED',result=?,settlement_price=?,pnl=?,closed_ts=? WHERE window=? AND status='OPEN'",(result,end,round(pnl,4),t['window']+900,t['window']))

def reset_paper_ledger():
    """Archive and reset ONLY the simulated trade ledger; retain signals and settings.

    A single SQLite transaction makes the snapshot and reset atomic even if the
    worker is running. The current window's decision remains in place so a reset
    cannot accidentally open a second paper entry in that window.
    """
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS paper_trade_reset_archive (id INTEGER PRIMARY KEY AUTOINCREMENT, reset_ts INTEGER NOT NULL, trade_json TEXT NOT NULL)')
        records=[dict(r) for r in c.execute('SELECT * FROM paper_trades ORDER BY window')]
        reset_ts=int(time.time())
        if records:
            c.executemany('INSERT INTO paper_trade_reset_archive(reset_ts,trade_json) VALUES(?,?)',
                          [(reset_ts,json.dumps(r,default=str)) for r in records])
            c.execute('DELETE FROM paper_trades')
        return len(records)

def paper_trades(limit=500):
    with conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM paper_trades ORDER BY window DESC LIMIT ?',(limit,))]
