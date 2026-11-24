"""Print the current market, exact diagnostic reason, and quote data; no trades."""
import datetime as dt
import time
import engine

def main():
    now=int(time.time());w=now//900*900
    print('Database:',engine.DB.resolve())
    print('UTC:',dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat())
    print('Window closes:',dt.datetime.fromtimestamp(w+900,dt.timezone.utc).isoformat())
    print('Call:',engine.setting('call_enabled','1'), 'mode:',engine.setting('call_mode','Display only'))
    print('Quant Gate:',engine.setting('gate_enabled','1'), 'minute:',engine.setting('call_minute',6))
    for row in engine.read_decisions(4):
        print('Decision:',row['window'],row['side'],row['reason'])
    try:
        market=engine.kalshi_market(w,now)
        print('MATCHED:',market['ticker'],'status:',market.get('status'),
              'close:',market.get('close_time'))
        for side in ('UP','DOWN'):
            try:
                q=engine.kalshi_entry_quote(w,now,side)
                print(side,'observed ask:',f"${q['ask']:.4f}",
                      'size:',q['quantity'],'source:',q['source'],'ticker:',q['ticker'])
            except Exception as exc:
                print(side,'QUOTE ERROR:',type(exc).__name__,str(exc))
    except Exception as exc:
        print('MARKET ERROR:',type(exc).__name__,str(exc))
    print('Diagnostic only. No real or paper orders placed.')
if __name__=='__main__':main()
