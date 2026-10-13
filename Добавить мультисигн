import time
from tronpy import Tron
from tronpy.providers import HTTPProvider
from tronpy.keys import PrivateKey

URL = "https://tron-mainnet.core.chainstack.com/СГЕНЕРИРУЙТЕ САМИ/wallet"
KEY_1 = input("Основной private key: ")
KEY_2 = input("Private key для мультисигна: ")

def setup():
    k1 = PrivateKey(bytes.fromhex(KEY_1))
    k2 = PrivateKey(bytes.fromhex(KEY_2))
    
    addr1 = k1.public_key.to_base58check_address()
    addr2 = k2.public_key.to_base58check_address()
    
    client = Tron(provider=HTTPProvider(URL))
    
    try:
        print(f"Getting permissions for {addr1}...")
        perm = client.get_account_permission(addr1)
        
        print(f"Adding guard: {addr2}")
        
        # Owner
        perm["owner"]["threshold"] = 2
        perm["owner"]["keys"] = [
            {"address": addr1, "weight": 1},
            {"address": addr2, "weight": 1}
        ]
        
        # Active
        for p in perm.get("actives", []):
            p["threshold"] = 2
            p["keys"] = [
                {"address": addr1, "weight": 1},
                {"address": addr2, "weight": 1}
            ]
            if "type" not in p:
                p["type"] = 1
                
        print("Sending update tx...")
        txn = client.trx.account_permission_update(addr1, perm).build()
        signed = txn.sign(k1)
        res = signed.broadcast()
        
        print(f"TxID: {res.get('txid', 'Unknown')}")
        print("Waiting 5s...")
        time.sleep(5)
        
        info = client.get_account(addr1)
        if 'owner_permission' in info and info['owner_permission'].get('threshold') == 2:
            print("\nSUCCESS! Multisig active.")
        else:
            print("Check status on Tronscan.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    setup()
