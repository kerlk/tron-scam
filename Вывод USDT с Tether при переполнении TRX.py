import asyncio
import time
import traceback
from getpass import getpass
from tronpy import AsyncTron
from tronpy.keys import PrivateKey
from tronpy.providers.async_http import AsyncHTTPProvider

# --- НАСТРОЙКИ ---
URL = "https://tron-mainnet.core.chainstack.com/СГЕНЕРИРУЙТЕ САМИ/wallet"
TO = "ВСТАВЬТЕ САМИ" #адрес получателя
TRX_MIN = 5.0  #когда на баллике больше 5 TRX, выводится USDT_AMT, этот параметр в комиссию идёт в общем
USDT_AMT = 170.0 #тут крч сколько вывести в баксах
USDT_DEC = 6
USDT_ADDR = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t" #не трожь
DELAY = 0.05 # опрос 20 раз в секунду 
LOG_TIME = 3600 #Логи раз в час
DBG_TIME = 1.0
MAX_REQ = 5
FEE_LIM = 50_000_000

class Monitor:
    def __init__(self, url, to_addr, multi=False):
        self.client = AsyncTron(provider=AsyncHTTPProvider(url))
        self.to = to_addr
        self.multi = multi
        self.keys = []
        self.addr = None
        self.contract = None
        
        self.iters = 0
        self.ok = 0
        self.err = 0
        self.t_dbg = time.time()
        self.t_log = time.time()
        self.busy = False
        self.sem = asyncio.Semaphore(MAX_REQ)

    async def start(self):
        await self.client.__aenter__()
        self.contract = await self.client.get_contract(USDT_ADDR)
        mode = "MULTISIG" if self.multi else "SINGLE"
        print(f"Mode: {mode} | Addr: {self.addr} | Rate: ~20/s")

    async def stop(self):
        try: await self.client.__aexit__(None, None, None)
        except: pass

    async def run(self):
        while True:
            t0 = time.time()
            self.iters += 1
            
            async with self.sem:
                try:
                    t_trx = self.client.get_account_balance(self.addr)
                    t_usdt = self.contract.functions.balanceOf(self.addr)
                    res_trx, res_usdt = await asyncio.gather(t_trx, t_usdt, return_exceptions=True)

                    if not isinstance(res_trx, Exception) and not isinstance(res_usdt, Exception):
                        self.ok += 1
                        bal_trx = float(res_trx)
                        bal_usdt = float(res_usdt) / (10 ** USDT_DEC)

                        if bal_trx > TRX_MIN and not self.busy:
                            print(f"\n[{time.strftime('%H:%M:%S')}] TRIGGER! TRX: {bal_trx:.4f}. Sending {USDT_AMT} USDT...")
                            self.busy = True
                            raw_amt = int(USDT_AMT * (10 ** USDT_DEC))
                            success = await self.send(raw_amt)
                            print("OK!" if success else "FAIL.")
                            await asyncio.sleep(5)
                            self.busy = False
                    else:
                        self.err += 1
                except Exception:
                    self.err += 1

            now = time.time()
            if now - self.t_dbg >= DBG_TIME:
                elapsed = now - self.t_dbg
                total_req = self.iters * 2
                total_ok = self.ok * 2
                speed = total_req / elapsed if elapsed > 0 else 0
                print(f"\r[DBG] Iters: {self.iters:<5} | Req: {total_req:<5} | OK: {total_ok:<5} | Err: {self.err:<3} | Spd: {speed:.1f} r/s", end="", flush=True)
                self.t_dbg = now

            if now - self.t_log >= LOG_TIME:
                print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Report: Iters: {self.iters}, OK: {self.ok}, Err: {self.err}")
                self.t_log = now

            sleep_t = max(0.001, DELAY - (time.time() - t0))
            await asyncio.sleep(sleep_t)

    async def send(self, amt_raw):
        try:
            txn = self.contract.functions.transfer(self.to, amt_raw).with_owner(self.addr).build(fee_limit=FEE_LIM)
            signed = txn.sign(self.keys[0])
            if self.multi and len(self.keys) > 1:
                signed = signed.sign(self.keys[1])
            
            result = await signed.broadcast()
            print(f"\nTxID: {result['txid']}")
            
            final = await asyncio.wait_for(result.wait(), timeout=30.0)
            c_res = final.get('contract_result', [])
            
            if c_res and c_res[0] == 'SUCCESS':
                return True
            else:
                print(f"Contract error: {c_res}")
                return False
        except asyncio.TimeoutError:
            print("Timeout.")
            return False
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()
            return False

async def main():
    print("="*50)
    print("   AUTO MONITOR & SEND USDT")
    print("="*50)
    print("1. Single Key")
    print("2. Multisig (2 Keys)")
    
    choice = input("\nChoice (1 or 2): ").strip()
    keys_hex = []
    is_multi = False

    if choice == '2':
        is_multi = True
        k1 = getpass("Key 1 (hex): ").strip()
        k2 = getpass("Key 2 (hex): ").strip()
        if not k1 or not k2:
            print("Error: Keys required!")
            return
        keys_hex = [k1, k2]
    elif choice == '1':
        k1 = getpass("Key (hex): ").strip()
        if not k1:
            print("Error: Key required!")
            return
        keys_hex = [k1]
    else:
        print("Invalid choice.")
        return

    m = Monitor(URL, TO, multi=is_multi)
    m.keys = [PrivateKey(bytes.fromhex(k)) for k in keys_hex]
    m.addr = m.keys[0].public_key.to_base58check_address()

    if is_multi:
        addr2 = m.keys[1].public_key.to_base58check_address()
        print(f"Guard Addr: {addr2}")

    try:
        await m.start()
        await m.run()
    except KeyboardInterrupt:
        print("\n\nStop.")
    finally:
        await m.stop()

if __name__ == "__main__":
    asyncio.run(main())
