import time, datetime as dt, json, html, math
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd
from engine import feed,process,read_layer,read_decisions,setting,set_setting,window_stats,bootstrap_history,paper_trades,reset_paper_ledger

st.set_page_config(page_title='Call Gate Style | BTC15 Paper Bot',page_icon='🟢',layout='wide',initial_sidebar_state='collapsed')
# Optional access gate for public Streamlit Cloud deployments.
# Set APP_PASSWORD as a Streamlit app secret; do not commit secrets to GitHub.
import os
try:
    cloud_password = str(st.secrets.get('APP_PASSWORD', '')).strip()
except Exception:
    cloud_password = ''
if cloud_password:
    import hmac
    if not st.session_state.get('authenticated', False):
        st.title('🔒 BTC15 Private Paper Dashboard')
        entered=st.text_input('Dashboard password',type='password')
        if st.button('Unlock dashboard'):
            if hmac.compare_digest(entered,cloud_password):
                st.session_state['authenticated']=True
                st.rerun()
            else:
                st.error('Incorrect password')
        st.stop()
else:
    st.warning('No APP_PASSWORD configured. Anyone with the public app link may access bot settings and paper history. Set APP_PASSWORD in Streamlit Cloud secrets before sharing.')
st.markdown('''<style>
:root{color-scheme:dark}
.stApp{background:radial-gradient(ellipse at 70% -15%,#1a222d 0%,#0a0e15 53%,#070a10 100%);color:#e4ecf1}
.block-container{max-width:1320px;padding:1rem 1.1rem 3rem}
header[data-testid="stHeader"]{background:transparent}
h1{font-size:1.48rem!important;letter-spacing:-.02em} h2,h3,h4{color:#f3f8fb!important}
p,li{color:#d2dde7}
.bx{background:linear-gradient(125deg,rgba(25,38,54,.95),rgba(31,48,70,.94));border:1px solid #43576c;border-radius:12px;padding:15px 17px;margin:3px 0 10px;min-height:95px}
.darkbx{background:#0d1622;border:1px solid #3d5166;border-radius:11px;padding:13px 15px;margin:3px 0 8px;min-height:90px}
.cap{font-weight:750;letter-spacing:.105em;color:#a6bac8;font-size:.71rem;text-transform:uppercase}
.val{font-weight:750;color:#f4faff;font-size:1.47rem;line-height:1.53}
.small{font-size:.82rem;color:#b4c5d1}.up{color:#59edac!important}.down{color:#ff879e!important}.warn{color:#f7d280!important}
.strip{display:flex;gap:5px;margin:9px 0;overflow:hidden}.pill{min-width:16px;flex:1;text-align:center;padding:5px 0;background:#233346;border:1px solid #557089;border-radius:5px;font-weight:800}
div[data-testid="stVerticalBlockBorderWrapper"]{border:1px solid #3f4e60;background:linear-gradient(115deg,rgba(19,29,42,.98),rgba(25,37,52,.95));border-radius:13px}
.stButton button{background:#123c30!important;color:#93ffd2!important;border:1px solid #34775b!important}
[data-testid="stMetric"]{background:#152437;border:1px solid #364c65;padding:12px;border-radius:12px}
div[data-testid="stRadio"] label{font-size:.83rem}
div[data-testid="stToggle"]{padding-top:.2rem}
.stTabs [data-baseweb="tab"]{font-size:.82rem}
div[data-testid="stAlert"]{background-color:#16283a!important;color:#ecf4fa!important;border:1px solid #435b6a!important;border-radius:9px!important}
div[data-testid="stAlert"] p,div[data-testid="stAlert"] span{color:#f4f7fc!important}
[data-testid="stDataFrame"]{border:1px solid #405368;border-radius:9px}
[data-testid="stNumberInput"] input{background:#182639!important;color:#ecf6ff!important}
[data-testid="stProgress"]>div>div{background:#67eab5!important}
@media(max-width:700px){
.block-container{padding:.5rem .55rem 3rem!important}
.bx,.darkbx{padding:10px 11px;min-height:72px;margin:3px 0 7px}
.val{font-size:1.12rem;overflow-wrap:anywhere}
h1{font-size:1.18rem!important}
h3{font-size:1.03rem!important}
[data-testid='stHorizontalBlock']{gap:.45rem!important}
[data-testid='column']{min-width:0!important}
[data-testid='stRadio'] [role='radiogroup']{flex-wrap:wrap!important;gap:.3rem!important}
[data-testid='stDataFrame']{max-width:100%;overflow:auto}
button{white-space:normal!important}
.stCaptionContainer, .stMarkdown p{overflow-wrap:anywhere}
}
</style>''',unsafe_allow_html=True)
Z=ZoneInfo('America/New_York');now=int(time.time());window=now//900*900;elapsed=now-window
fmt=lambda ts:dt.datetime.fromtimestamp(ts,Z).strftime('%-I:%M %p') if not __import__('os').name=='nt' else dt.datetime.fromtimestamp(ts,Z).strftime('%I:%M %p').lstrip('0')
def fmtwin(w):return f'{fmt(w)}–{fmt(w+900)} ET'
def safe(s):return html.escape(str(s))
def box(title,value,detail='',dark=False,kind=''):
    st.markdown(f'<div class="{"darkbx" if dark else "bx"}"><div class="cap">{safe(title)}</div><div class="val {kind}">{safe(value)}</div><div class="small">{safe(detail)}</div></div>',unsafe_allow_html=True)
def signalword(s):return ('↑ UP' if s=='UP' else '↓ DOWN' if s=='DOWN' else '⚠ Skip this window' if s=='SKIP' else '⌛ Silent')
def current(rows):return next((r for r in rows if r['window']==window),None)
def evidence(r):
    try:return json.loads(r['evidence']) if r else {}
    except (TypeError,ValueError):return {}
def tracker(title,rows):
    rows=rows[:100];graded=[r for r in rows if r['outcome'] in ('WIN','LOSS')]
    wins=sum(r['outcome']=='WIN' for r in graded);losses=len(graded)-wins
    percentage=f'{100*wins/len(graded):.1f}%' if graded else '—'
    st.markdown(f'<span class="cap">{safe(title)}</span> &nbsp; <span class="small">{wins} correct of {len(graded)} graded · {percentage}</span>',unsafe_allow_html=True)
    colors={'WIN':('#71f2c3','✓'),'LOSS':('#ff96a8','×'),'SKIP':('#ffd483','△')}
    snippets=[]
    for r in rows[:12]:
        color,mark=colors.get(r['outcome'],('#7896b5','·'))
        snippets.append(f'<span class="pill" style="color:{color}">{mark}</span>')
    st.markdown('<div class="strip">'+''.join(snippets or ['<span class="small">No graded observations yet</span>'])+'</div>',unsafe_allow_html=True)
    st.caption(f'{losses} wrong · {sum(r["side"]=="SKIP" for r in rows)} skipped · {sum(r["outcome"] is None for r in rows)} pending · skips excluded from win rate')
def setting_toggle(key,caption,default='1'):
    prev=setting(key,default);val=st.toggle(caption,value=prev=='1',key=key)
    if val!=(prev=='1'):set_setting(key,'1' if val else '0')
    return val

st.title('🟢 BTC15 · PHONE PAPER BOT')
st.caption('GitHub + Streamlit Cloud · BTC 15-minute windows · paper only · no chart')
st.info('CLOUD LIMITATION: Data is collected while this page is active. Streamlit Community Cloud may sleep, restart, or delete local SQLite data. Do not treat this as a continuous 24/7 worker or durable historical ledger.')
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=20000,key='refresh')
except ImportError:st.warning('Install requirements to enable automatic refresh.')
@st.cache_data(ttl=18,show_spinner=False)
def live_feed():return feed()
@st.cache_data(ttl=3600,show_spinner=False)
def backfill():bootstrap_history();return True
candles={};price=None;online=False
try:
    backfill();candles,price=live_feed();process(candles,price,now);online=True
except Exception as exc:st.error(f'BTC price feed unavailable: {exc}. The dashboard will not fabricate prices or signals.')
call=read_layer('call');quant=read_layer('quant');learning=read_layer('learning');decisions=read_decisions()
s=window_stats(candles,now,price) if online else {}
trades=paper_trades()

# PHONE QUICK READ — mirrors active signal and paper totals without requiring scrolling.
latest_call=next((r for r in call if r['window']==window),None)
latest_quant=next((r for r in quant if r['window']==window),None)
valid_quotes=[t for t in trades if t.get('entry_source') in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK')]
settled_quotes=[t for t in valid_quotes if t['status']=='CLOSED' and t['result'] in ('WIN','LOSS')]
net_quotes=sum(float(t['pnl']) for t in settled_quotes)
st.markdown('''<div class="cap" style="margin-bottom:6px">PHONE QUICK STATUS · PAPER ONLY</div>''',unsafe_allow_html=True)
statuscols=st.columns(3)
with statuscols[0]:box('CALL',signalword(latest_call['side']) if latest_call else 'WAITING',f'Locks at minute {setting("call_minute",6)}',kind='up' if latest_call and latest_call['side']=='UP' else 'down' if latest_call and latest_call['side']=='DOWN' else '')
with statuscols[1]:box('QUANT GATE',signalword(latest_quant['side']) if latest_quant else 'WAITING','3 readings must agree')
with statuscols[2]:box('PAPER NET',f'${net_quotes:+,.2f}',f'{len(settled_quotes)} settled · $10 max/entry',kind='up' if net_quotes>=0 else 'down')
# MARKET HEADER — no chart
st.markdown('**CRYPTO**　　<span class="up">● BTC</span>　　**15 min**　　<span class="up">● LIVE FEED</span>　　**CALLS / PAPER TRADING**' if online else '**CRYPTO**　　BTC　　15 min　　● FEED OFFLINE',unsafe_allow_html=True)
with st.container(border=True):
    a,b=st.columns([1,1])
    with a:
        box('TIME LEFT IN WINDOW',f'{(900-elapsed)//60:02d}:{(900-elapsed)%60:02d}',fmtwin(window))
        st.progress(elapsed/900)
    with b:
        box('BTC NOW · COINBASE',f'${price:,.2f}' if price else 'Unavailable',f'Window open: ${s["window_open"]:,.2f}' if s else 'Waiting for complete price data',kind='up' if s and s['gap']>=0 else 'down')
    st.caption('Target is the BTC/USD spot price at the 15-minute window open. The screenshot website may use different feeds/market reference strikes.')

with st.container(border=True):
    a,b=st.columns(2)
    with a:
        st.markdown('#### 15-minute up/down counter')
        c,d=st.columns(2)
        with c:box('↑ UP',s.get('ups','—'),'Recently completed windows',kind='up')
        with d:box('↓ DOWN',s.get('downs','—'),'Recently completed windows',kind='down')
        st.caption(f'{s.get("history_count",0)} settled BTC spot windows observed; counter summarizes last 12')
    with b:
        st.markdown('#### Where BTC stands')
        box('WINDOW OPEN',f'${s["window_open"]:,.2f}' if s else '—',fmtwin(window))
        c,d=st.columns(2)
        with c:box('DISTANCE FROM TARGET',f'${s["gap"]:+,.2f}' if s else '—','Current spot minus window open',kind='up' if s and s['gap']>=0 else 'down')
        with d:box('GAP PER MINUTE LEFT',f'${s["per_min"]:,.2f}' if s else '—','Required per-minute gain to finish above open')
        c,d=st.columns(2)
        with c:box('1 MIN',f'${price-s["past1"]:+,.2f}' if s and s['past1'] is not None else '—',dark=True)
        with d:box('5 MIN',f'${price-s["past5"]:+,.2f}' if s and s['past5'] is not None else '—',dark=True)

with st.container(border=True):
    a,b=st.columns(2)
    with a:
        st.markdown('#### Move needed')
        box('BTC MUST RISE TO FINISH ABOVE OPEN',f'${s["needed"]:,.2f}' if s else '—',f'{(900-elapsed)//60}m {(900-elapsed)%60}s remaining' if s else 'Awaiting data',kind='up')
        st.caption('A required movement calculation, **not** a probability or guaranteed outcome.')
    with b:
        st.markdown('#### How much BTC has been moving')
        c,d=st.columns(2)
        with c:box('TYPICAL 1-MIN MOVE',f'±${s["typical1"]:,.2f}' if s and s['typical1'] is not None else '—','Absolute 1m price body',dark=True)
        with d:box('TYPICAL 15-MIN MOVE',f'±${s["typical"]:,.2f}' if s and s['typical'] is not None else '—','Mean completed window net change',dark=True)
        st.caption('Real historical spot price movements; average absolute movement is not an implied forecast.')

with st.container(border=True):
    a,b=st.columns(2)
    with a:
        st.markdown('#### Candle lean')
        if s and len(s['completed'])>=12:
            recent=s['completed'][-12:];total=sum(delta for _,delta in recent);up=sum(delta>0 for _,delta in recent)
            box('LAST 12 WINDOWS',('UP' if total>0 else 'DOWN' if total<0 else 'FLAT'),f'{up} green · {len(recent)-up} red · net ${total:+,.2f}',kind='up' if total>=0 else 'down')
        else:box('READING STORED HISTORY','Waiting for sufficient history','Requires at least 12 recorded complete windows')
    with b:
        st.markdown('#### Market edge')
        box('KALSHI / POLYMARKET CONTRACT ODDS','Unavailable','No verified live quote integration; edge cannot be calculated',kind='warn')
        st.caption('A genuine edge needs an identified market, contract price, a calibrated prediction, fees, and real executable quotes. No implied odds are invented.')

with st.container(border=True):
    a,b=st.columns(2)
    with a:
        st.markdown('#### Window history')
        recent=(s.get('completed') or [])[-12:][::-1]
        if recent:
            st.dataframe(pd.DataFrame([{'Window (ET)':fmtwin(w),'Direction':'UP' if delta>0 else 'DOWN' if delta<0 else 'TIE','Net BTC change':round(delta,2)} for w,delta in recent]),hide_index=True,use_container_width=True,height=270)
        else:st.caption('Waiting for settled price windows')
    with b:
        st.markdown('#### Typical 15-min move by hour')
        bh=s.get('byhour',{})
        if bh:
            st.dataframe(pd.DataFrame([{'UTC hour':f'{i:02d}:00','Mean absolute move':f'${bh[i]:,.2f}'} for i in sorted(bh)]),hide_index=True,use_container_width=True,height=270)
        else:st.caption('Accumulating historical completed windows')

with st.container(border=True):
    a,b=st.columns([5,1])
    with a:st.markdown('### 📞 Call');st.caption('Buys YES on UP and NO on DOWN in hypothetical paper mode when two readings agree.')
    with b:setting_toggle('call_enabled','ON')
    modes=['Display only','Display, then confirm','Place trades automatically']
    prev=setting('call_mode',modes[0]); mode=st.radio('EXECUTION MODE',modes,index=modes.index(prev) if prev in modes else 0,horizontal=True,key='mode')
    if mode!=prev:set_setting('call_mode',mode)
    minute=int(setting('call_minute','6'))
    m=st.number_input('SIGNAL TIMING · minute 1–14',1,14,minute,help='If changed mid-window, previously locked predictions are never retroactively changed.')
    if m!=minute:set_setting('call_minute',m)
    cr=current(call);a,b=st.columns(2)
    with a:box('SIGNAL TIMING','Locked' if cr else 'Silent',f'Minute {minute} of 15 · read held through the window')
    with b:box('CALL',signalword(cr['side']) if cr else '⌛ Silent',f'Confidence {cr["confidence"]:.1f}%' if cr else f'Waiting until minute {minute}',kind='up' if cr and cr['side']=='UP' else 'down' if cr and cr['side']=='DOWN' else '')
    st.markdown('**TWO READINGS, MINUTE '+str(minute)+'** · must agree')
    vals=evidence(cr).get('readings',[])
    a,b=st.columns(2)
    with a:box('CURRENT RULE',signalword(vals[0]) if len(vals)>0 else '—',dark=True)
    with b:box('3-FACTOR SCORE',signalword(vals[1]) if len(vals)>1 else '—',dark=True)
    if cr:st.info('✓ Agreed — Call locked for the window' if cr['side'] in ('UP','DOWN') else '⚠ Skip this window — readings do not agree or market conditions do not qualify')
    tracker('ROLLING 100 CALLS',call)

with st.container(border=True):
    a,b=st.columns([5,1])
    with a:st.markdown('### 🧠 Quant gate');st.caption('Three readings, one decision. When enabled, a conflicting gate prevents a simulated automatic entry.')
    with b:setting_toggle('gate_enabled','ON')
    qmode=setting('gate_mode','Display only')
    qnew=st.radio('QUANT EXECUTION MODE',modes,index=modes.index(qmode) if qmode in modes else 0,horizontal=True,key='quant_mode')
    if qnew!=qmode:set_setting('gate_mode',qnew)
    qr=current(quant);a,b=st.columns(2)
    with a:box('SIGNAL TIMING','Locked' if qr else 'Silent',f'Minute {minute} · shared with Call')
    with b:box('QUANT',signalword(qr['side']) if qr else '⌛ Silent','Advisory unless gate is enabled',kind='up' if qr and qr['side']=='UP' else 'down' if qr and qr['side']=='DOWN' else '')
    st.markdown('**THREE READINGS, ONE ORDER** · all must agree')
    vals=evidence(qr).get('readings',[])
    a,b,c=st.columns(3)
    with a:box('READING 1',signalword(vals[0]) if len(vals)>0 else '—',dark=True)
    with b:box('READING 2',signalword(vals[1]) if len(vals)>1 else '—',dark=True)
    with c:box('FINAL CHECK',signalword(vals[2]) if len(vals)>2 else '—',dark=True)
    if qr:st.info('✓ All agree' if qr['side']!='SKIP' else '⚠ Skip this window — three readings do not agree')
    tracker('ROLLING 100 QUANT READS',quant)
    st.caption('Quant Gate display mode is informational. Simulated entry selection is controlled by the Call mode; Quant Gate can veto, but never create an entry.')

with st.container(border=True):
    st.markdown('### 🧩 Learning Call')
    st.caption('Historical-analogue predictions using previously completed 15-minute BTC windows. Locked after four complete minutes.')
    lr=current(learning);a,b=st.columns(2)
    with a:box('WINDOW STATUS','Locked in for this window' if lr else 'Waiting for completed price data',f'{len(learning)} recorded learning reads')
    with b:box('PREDICTED CALL',signalword(lr['side']) if lr else 'Waiting for data',f'{lr["confidence"]:.1f}% model estimate' if lr else 'Awaiting minute 4')
    st.caption('Requires 25 completed historical windows to activate. Model probabilities are empirical estimates, not calibrated contract win probabilities.')
    tracker('LEARNING CALL TRACKER',learning)

with st.container(border=True):
    st.markdown('### 💵 PAPER PROFIT / LOSS & WINS')
    st.caption('NEW entries use observed public Kalshi best-ask quotes (YES for UP, NO for DOWN). Quotes are NOT confirmed fills. Fees remain configurable estimates. Older 50¢-assumption trades are displayed separately and never mislabeled as market quotes.')
    quoted=[t for t in trades if t.get('entry_source') in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK')]
    finished=[t for t in quoted if t['status']=='CLOSED' and t['result'] in ('WIN','LOSS')]
    wins=sum(t['result']=='WIN' for t in finished)
    losses=sum(t['result']=='LOSS' for t in finished)
    pnl=sum(float(t['pnl']) for t in finished)
    open_trades=[t for t in quoted if t['status']=='OPEN']
    d1,d2,d3,d4=st.columns(4)
    with d1:box('NET QUOTED PAPER P&L',f'${pnl:+,.2f}',f'{len(finished)} settled quote-based paper trades',kind='up' if pnl>=0 else 'down')
    with d2:box('WINS',str(wins),'Settled winning entries',kind='up')
    with d3:box('LOSSES',str(losses),'Settled losing entries',kind='down')
    with d4:box('PAPER WIN RATE',f'{100*wins/len(finished):.1f}%' if finished else '—',f'{len(open_trades)} open positions')
    with st.expander('Paper trade budget & fee ESTIMATE (new entries only)'):
        st.caption('Entry prices come from the real Kalshi order book, NOT from the old 50¢ setting. Actual fills may be worse, may be unavailable, or may not happen at all. Fees are still an estimated flat amount per contract.')
        st.info('Fixed paper budget: **$10.00 maximum per new entry**, including estimated fees. Only whole contracts can be simulated, so total spent may be slightly below $10. This is not a live-money purchase.')
        old=float(setting('paper_fee_cents','1'))
        new=st.number_input('Estimated fee per contract (¢)',min_value=0.0,max_value=20.0,value=old,step=0.5)
        if new!=old:set_setting('paper_fee_cents',new)
    with st.expander('Reset paper profit / losses / wins'):
        st.warning('Resets ALL paper trades (including legacy assumed-price trades and open positions) to $0 P&L, 0 wins, and 0 losses. Signal accuracy, Call, Quant Gate, Learning Call and bot settings stay unchanged. Old paper trades are archived in the local SQLite database.')
        confirm_reset=st.checkbox('I understand: reset the complete paper-trading ledger',key='confirm_reset_paper')
        if st.button('Reset paper P&L to $0',disabled=not confirm_reset,type='primary'):
            reset_count=reset_paper_ledger()
            st.session_state['paper_reset_message']=f'Paper ledger reset: {reset_count} trades archived. Your P&L, wins and losses now start at zero.'
            st.rerun()
    if st.session_state.get('paper_reset_message'):
        st.success(st.session_state.pop('paper_reset_message'))
    st.caption('New paper entries require a valid active KXBTC15M market and a live best ask. Without one, the entry is skipped. Kalshi official market results determine new trade wins/losses; paper P&L is still estimated because no actual fills occurred.')
    if trades:
        display=pd.DataFrame(trades).copy()
        display['Window ET']=display['window'].map(fmtwin)
        display['Paper P&L ($)']=display['pnl'].map(lambda x: f'${x:+,.2f}' if x is not None else 'OPEN')
        display['Observed entry ask (¢)']=display.apply(lambda r:round(r['assumed_entry_price']*100,2) if r['entry_source'] in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK') else None,axis=1)
        display['Legacy assumed (¢)']=display.apply(lambda r:round(r['assumed_entry_price']*100,2) if r['entry_source'] not in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK') else None,axis=1)
        display['Quote ET']=display['quote_ts'].map(lambda x:fmt(int(x)) if pd.notna(x) else '—')
        display['Cost + fee ($)']=display['entry_cost'].round(2)
        st.dataframe(display[['Window ET','side','status','result','entry_source','market_ticker','Quote ET','Observed entry ask (¢)','Legacy assumed (¢)','contracts','Cost + fee ($)','Paper P&L ($)']],hide_index=True,use_container_width=True,height=300)
        previous=[t for t in trades if t.get('entry_source') not in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK') and t['status']=='CLOSED' and t['pnl'] is not None]
        if previous:st.info(f'LEGACY assumed-price history: {len(previous)} settled paper entries, illustrative net P&L ${sum(float(t["pnl"]) for t in previous):+,.2f}. Excluded from quote-based totals above.')
        st.download_button('Download paper P&L CSV',display.to_csv(index=False).encode(),'btc15_paper_pnl.csv','text/csv')
    else:
        st.info('No automatic paper entries yet. Choose “Place trades automatically” in Call to begin collecting simulated results. The worker must remain running.')

with st.container(border=True):
    st.markdown('### 🧾 Paper bot & decisions')
    decision=next((r for r in decisions if r['window']==window),None)
    box('CURRENT 15-MIN DECISION',signalword(decision['side']) if decision else 'Waiting for Call',decision['reason'] if decision else 'Evaluating at selected Call minute')
    if decision and decision['side']!='SKIP' and decision['mode']=='Display, then confirm':
        ack=st.checkbox('I confirm this paper signal (no real order)',key=f'ack_{window}')
        st.info('Paper signal confirmed in this browser view.' if ack else 'Awaiting manual confirmation in this browser view.')
    st.caption('Automatic remains PAPER-ONLY: reads public Kalshi KXBTC15M best-ask quotes and official market results, without orders or account credentials. No guaranteed fills; fee estimates and available size may differ from actual trading. Missing market quotes mean NO paper trade.')
    if decisions:
        df=pd.DataFrame(decisions);df['Window ET']=df['window'].map(fmtwin)
        st.dataframe(df[['Window ET','side','mode','price','reason']],hide_index=True,use_container_width=True)

with st.expander('Full prediction history / CSV downloads'):
    choice=st.selectbox('Signal layer',['call','quant','learning'])
    rows=read_layer(choice)
    if rows:
        df=pd.DataFrame(rows);df['Window ET']=df['window'].map(fmtwin)
        st.dataframe(df[['Window ET','side','confidence','spot','outcome','close_price']],hide_index=True,use_container_width=True)
        st.download_button('Download CSV',df.to_csv(index=False).encode(),f'{choice}_btc15.csv','text/csv')
    else:st.caption('No samples yet')
st.caption('Cloud dashboard collects only while open; SQLite may reset on restart. Research-only. Signals are original transparent rules, not a replica of the private model in the screenshots. Accuracy grades spot window direction using Coinbase 1-minute candles; skips are excluded. Always-on tracking requires worker.py and persistent storage.')
