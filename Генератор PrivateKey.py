from tronpy.hdwallet import seed_from_mnemonic, key_from_seed
from tronpy.keys import PrivateKey

print("Ожидайте...")
raw = input("Введите seed: ")
mnemonic = " ".join(raw.strip().lower().split())

if not mnemonic:
    print("Ошибка: Ввод пустой.")
else:
    try:
        seed = seed_from_mnemonic(mnemonic, passphrase="")
        path = "m/44'/195'/0'/0/0"
        priv_bytes = key_from_seed(seed, account_path=path)
        priv = PrivateKey(priv_bytes)
        
        print("\nPK:", priv.hex())
        print("Адрес:", priv.public_key.to_base58check_address())
    except Exception as e:
        print(f"Error: {type(e).__name__} - {e}")

input("\nНажмите Enter для выхода")
