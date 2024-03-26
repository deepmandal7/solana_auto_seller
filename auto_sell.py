
    

import requests
from loguru import logger
import json
from solana.rpc.api import Client
from solana.rpc.commitment import Commitment
from solders.keypair import Keypair
import sys
from configparser import ConfigParser
import base58, logging,time, re, os,sys, json
from raydium.Raydium import *
import requests


def get_assets_by_owner(RPC_URL, wallet_address):
    logger.info("Checking Wallet for New Tokens")
    payload = {
        "jsonrpc": "2.0",
        "id": "my-id",
        "method": "getAssetsByOwner",
        "params": {
            "ownerAddress": wallet_address,
            "page": 1,  # Starts at 1
            "limit": 1000,
            "displayOptions": {
                "showFungible": True,
                "showNativeBalance": True,
            }
        }
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(RPC_URL, headers=headers, json=payload)
    spl_tokens = []
    if response.status_code == 200:
        data = response.json()
        if "result" in data:
            assets = data["result"]["items"]
            for asset in assets:
                interface_type = asset.get("interface", "")
                if interface_type == "V1_NFT":
                    continue  # Skip NFT assets
                token_info = asset.get("token_info", {})
                balance = token_info.get("balance", None)
                price_info = token_info.get("price_info")
                if balance and float(balance) > 0 and price_info is not None:
                    spl_tokens.append({
                        "id": asset["id"],
                        "symbol": token_info.get("symbol", ""),
                        "balance": balance,
                        "token_info": token_info,
                        "price": price_info["total_price"]
                    })
            for token in spl_tokens:
                logger.info("Token ID: {}", token["id"])
                logger.info("Symbol: {}", token["symbol"])
                logger.info("Balance: {}", token["balance"])
                logger.info("Price: {}", token["price"])
                logger.info("Metadata: {}", token["token_info"])
        else:
            logger.error("No result found in response")
    else:
        logger.error("Error: {}, {}", response.status_code, response.text)
        
        
    logger.info(f"Current SPL Tokens {spl_tokens}")
    return spl_tokens

def write_wallet_tokens(tokens, wallet_tx_list_url, birdeye_x_api_key):
    

    # clear wallet_tokens.json if no SPL tokens are detected
    if not tokens:
        with open("data/wallet_tokens.json", "w") as file:
            file.write("[]")
        logger.info("Wallet tokens JSON file cleared")
        return
    
    current_time = int(time.time())
    
    # Load existing data from the JSON file
    try:
        with open("data/wallet_tokens.json", "r") as file:
            existing_tokens = json.load(file)
    except FileNotFoundError:
        existing_tokens = []

    last_swap_tx = get_last_swap_tx(wallet_tx_list_url)

    # Filter out existing tokens and add new tokens using list comprehensions
    new_tokens = [
        {
            "symbol": token.get("token_info", {}).get("symbol", ""),
            "token_id": token.get("id"),
            "balance": token.get("token_info", {}).get("balance", ""),
            "detection_time": current_time,
            "price": last_swap_tx["tokenTransfers"][0]["tokenAmount"] * get_token_current_price(birdeye_x_api_key, "So11111111111111111111111111111111111111112")
        }
        for token in tokens
        if not any(existing_token.get("token_id") == token.get("id") for existing_token in existing_tokens)
    ]

    # Append new tokens to the existing data
    existing_tokens.extend(new_tokens)

    # Write the updated data back to the JSON file
    with open("data/wallet_tokens.json", "w") as file:
        json.dump(existing_tokens, file, indent=4)

def get_last_swap_tx(wallet_tx_list_url):
    response = requests.get(wallet_tx_list_url)

    return json.loads(response.text)[1]

def get_token_current_price(birdeye_x_api_key, token):
    url = "https://public-api.birdeye.so/public/price?address=%s" % (token)

    headers = {"X-API-KEY": birdeye_x_api_key}

    response = requests.get(url, headers=headers)

    return json.loads(response.text)["data"]["value"]

def detect_old_tokens(birdeye_x_api_key, json_file, percentage):
    try:
        with open(json_file, "r") as file:
            existing_tokens = json.load(file)
    except FileNotFoundError:
        existing_tokens = []

    # Initialize the list to store tokens that meet the condition
    old_tokens = []

    # Loop over existing_tokens to calculate current_token_price for each token
    for token in existing_tokens:
        current_token_price = get_token_current_price(birdeye_x_api_key, token["token_id"])
        # Check if the current price meets the condition
        if current_token_price >= (percentage * token["price"] + token["price"]):
            old_tokens.append(token)

    return old_tokens


def remove_token_from_json(token_id):
    json_file = "data/wallet_tokens.json"
    
    try:
        # Load existing data from the JSON file
        with open(json_file, "r") as file:
            existing_tokens = json.load(file)
    except FileNotFoundError:
        # If the file doesn't exist, there's nothing to remove
        return

    # Filter out the token to be removed
    updated_tokens = [token for token in existing_tokens if token.get("token_id") != token_id]

    # Write the updated data back to the JSON file
    with open(json_file, "w") as file:
        json.dump(updated_tokens, file, indent=4)


def main():
    
    # Load Configs
    config = ConfigParser()
    config.read(os.path.join(sys.path[0], 'data', 'config.ini'))
    
    # Infura settings - register at infura and get your mainnet url.
    RPC_HTTPS_URL = config.get("DEFAULT", "SOLANA_RPC_URL")
    # Wallet tx list url
    wallet_tx_list_url = config.get("DEFAULT", "WALLET_TX_LIST_URL")
    # Birdeye x_api_key
    birdeye_x_api_key = config.get("DEFAULT", "BIRDEYE_X_API_KEY")
    # Wallet Address
    wallet_address = config.get("DEFAULT", "WALLET_ADDRESS")
    # Wallets private key
    private_key = config.get("DEFAULT", "PRIVATE_KEY")
    # Profit percentage
    percentage = int(config.get("DEFAULT", "PERCENTAGE")) / 100
    # Transfer fee
    transfer_fee = float(config.get("DEFAULT", ("TRANSFER_FEE")))
    # Slippage percentage
    slippage = int(config.get("DEFAULT", "SLIPPAGE"))
    
    ctx = Client(RPC_HTTPS_URL, commitment=Commitment("confirmed"), timeout=30,blockhash_cache=True)
    payer = Keypair.from_bytes(base58.b58decode(private_key))
    
    while True:
        spl_tokens = get_assets_by_owner(RPC_URL=RPC_HTTPS_URL, wallet_address=wallet_address)
        write_wallet_tokens(spl_tokens, wallet_tx_list_url=wallet_tx_list_url, birdeye_x_api_key=birdeye_x_api_key)

        # Detect and process old tokens
        
        old_tokens = detect_old_tokens(birdeye_x_api_key=birdeye_x_api_key, json_file="data/wallet_tokens.json", percentage=percentage)
        for token in old_tokens:
            logger.info(f"Detected old token: {token}. Selling now.")
            try:
                raydium_swap(ctx=ctx, payer=payer, desired_token_address=token['token_id'], transfer_fee=transfer_fee, slippage=slippage)
                remove_token_from_json(token_id=token['token_id'])
            except Exception as e:
                logger.warning(f"Issue encountered during sell {e}")    

        # Pause for some time before the next iteration
        time.sleep(1)  # 1 second

if __name__ == "__main__":
    main()
