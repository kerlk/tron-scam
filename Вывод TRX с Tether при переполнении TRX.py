import asyncio
import traceback
from getpass import getpass
from tronpy import AsyncTron
from tronpy.keys import PrivateKey
from tronpy.providers.async_http import AsyncHTTPProvider

# --- НАСТРОЙКИ ---
URL = "https://tron-mainnet.core.chainstack.com/СГЕНЕРИРУЙТЕ САМИ/wallet"
TO = "САМИ ВСТАВЬТЕ"   # адрес получателя

BAL_TARGET = 0.165          # сколько TRX должно остаться на кошельке после отправки
MIN_SEND = 0.1              # минимальная сумма отправки (меньше — не трогаем)
DELAY = 0.5                 # пауза между итерациями опроса, сек
MAX_REQ = 5                 # макс. параллельных запросов

BW_COST = 268               # байт bandwidth на одну TransferContract (обычную)
BW_COST_MULTI = 335         # байт на multisig-транзакцию (~+67 на вторую подпись)
DEF_BW_LIM = 600            # дефолтный free bandwidth лимит, если поля нет в ответе
BURN_PER_BW = 1000          # SUN за байт bandwidth (getTransactionFee, константа сети)
FEE_SAFETY = 1.1            # +10% запас на округление/колебания


class Sweeper:
    def __init__(self, url, to_addr, multi=False):
        self.client = AsyncTron(provider=AsyncHTTPProvider(url))
        self.to = to_addr
        self.multi = multi
        self.keys = []
        self.addr = None
        self.sem = asyncio.Semaphore(MAX_REQ)
        # Размер транзакции зависит от наличия второй подписи
        self.bw_cost = BW_COST_MULTI if multi else BW_COST

    async def start(self):
        await self.client.__aenter__()
        mode = "MULTISIG" if self.multi else "SINGLE"
        print(f"Mode: {mode} | Addr: {self.addr}")
        print(f"Target Bal: {BAL_TARGET} TRX | Min Send: {MIN_SEND} TRX")
        print(f"BW Cost: {self.bw_cost} byte | Burn: {BURN_PER_BW} SUN/byte")

    async def stop(self):
        try:
            await self.client.__aexit__(None, None, None)
        except Exception:
            pass

    async def get_data(self):
        """Возвращает (balance_trx, available_bandwidth) или (None, None) при ошибке."""
        async with self.sem:
            try:
                bal = await self.client.get_account_balance(self.addr)
                acc = await self.client.get_account(self.addr)

                cur_bal = float(bal)

                # Free bandwidth
                used_bw = acc.get("free_net_usage", 0)
                lim_bw = acc.get("free_net_limit", DEF_BW_LIM)
                free_bw = max(0, lim_bw - used_bw)

                # Staked bandwidth (account_resource.NetWeight)
                res = acc.get("account_resource", {}) or {}
                staked_bw = res.get("NetWeight", 0) if "NetWeight" in res else 0

                total_bw = free_bw + staked_bw
                return cur_bal, total_bw
            except Exception as e:
                print(f"\nErr: {e}")
                return None, None

    def calc_fee(self, bw):
        """Считает, сколько TRX сожжётся при отправке."""
        if bw >= self.bw_cost:
            return 0.0
        missing = self.bw_cost - bw
        burn_trx = missing * BURN_PER_BW / 1_000_000
        return burn_trx * FEE_SAFETY

    async def send(self, amt_sun):
        async with self.sem:
            try:
                txn = self.client.trx.transfer(self.addr, self.to, amt_sun).build()
                signed = txn.sign(self.keys[0])
                if self.multi and len(self.keys) > 1:
                    signed = signed.sign(self.keys[1])

                res = await signed.broadcast()
                txid = res.get("txid", "Unknown")
                print(f"\nTxID: {txid}")

                # Ждём подтверждения, чтобы увидеть реальную комиссию
                try:
                    final = await asyncio.wait_for(res.wait(), timeout=30.0)
                    receipt = final.get("receipt", {}) or {}
                    net_fee = receipt.get("net_fee", 0)
                    net_usage = receipt.get("net_usage", 0)
                    if net_fee or net_usage:
                        print(
                            f"Confirmed | BW: {net_usage} | "
                            f"Fee: {net_fee / 1_000_000:.6f} TRX"
                        )
                    c_res = final.get("contract_result", [])
                    if c_res and c_res[0] != "SUCCESS":
                        print(f"Contract result: {c_res}")
                        return False
                except asyncio.TimeoutError:
                    print("Wait timeout, but broadcast done.")
                return True
            except Exception as e:
                print(f"\nSend Err: {e}")
                traceback.print_exc()
                return False

    async def run(self):
        while True:
            try:
                bal, bw = await self.get_data()
                if bal is None:
                    await asyncio.sleep(DELAY * 2)
                    continue

                fee = self.calc_fee(bw)

                status = "FREE" if fee == 0 else f"PAID (~{fee:.4f})"
                print(
                    f"\rBal: {bal:.6f} | BW: {bw} | Fee: {status}",
                    end="", flush=True
                )

                # Оставляем BAL_TARGET + fee (с запасом), отправляем остальное
                to_send = bal - BAL_TARGET - fee

                if to_send > MIN_SEND:
                    amt_sun = int(to_send * 1_000_000)   # округление ВНИЗ
                    real_send = amt_sun / 1_000_000
                    print(f"\nSending: {real_send:.6f} TRX (fee ~{fee:.4f})")
                    ok = await self.send(amt_sun)
                    if ok:
                        print("Waiting for update...")
                        await asyncio.sleep(10)
                    else:
                        print("Retry in 5s...")
                        await asyncio.sleep(5)
            except KeyboardInterrupt:
                print("\nStop.")
                break
            except Exception as e:
                print(f"\nLoop Err: {e}")
                await asyncio.sleep(5)

            await asyncio.sleep(DELAY)


async def main():
    print("=" * 50)
    print("   AUTO TRX SWEEPER")
    print("=" * 50)
    print("1. Single Key")
    print("2. Multisig (2 Keys)")

    choice = input("\nChoice (1 or 2): ").strip()
    keys_hex = []
    is_multi = False

    if choice == "2":
        is_multi = True
        k1 = getpass("Key 1 (hex): ").strip()
        k2 = getpass("Key 2 (hex): ").strip()
        if not k1 or not k2:
            print("Error: Keys required!")
            return
        keys_hex = [k1, k2]
    elif choice == "1":
        k1 = getpass("Key (hex): ").strip()
        if not k1:
            print("Error: Key required!")
            return
        keys_hex = [k1]
    else:
        print("Invalid choice.")
        return

    s = Sweeper(URL, TO, multi=is_multi)
    s.keys = [PrivateKey(bytes.fromhex(k)) for k in keys_hex]
    s.addr = s.keys[0].public_key.to_base58check_address()

    if is_multi:
        addr2 = s.keys[1].public_key.to_base58check_address()
        print(f"Guard Addr: {addr2}")

    try:
        await s.start()
        await s.run()
    except KeyboardInterrupt:
        print("\n\nStop.")
    finally:
        await s.stop()


if __name__ == "__main__":
    asyncio.run(main())
