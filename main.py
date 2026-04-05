import os
import time
import random
import requests
from datetime import datetime

# CONFIGURATION
PLAYER_ID = os.environ.get("PLAYER_ID")
COOKIE = os.environ.get("ROLI_COOKIE")
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
OUTBID_WEBHOOK_URL = os.environ.get("OUTBID_WEBHOOK")
LOG_WEBHOOK_URL = os.environ.get("LOG_WEBHOOK") or OUTBID_WEBHOOK_URL
MONITOR_OUTBID = os.environ.get("MONITOR_OUTBID", "true").lower() == "true"
WEBSHARE_URL = os.environ.get("WEBSHARE_API_URL")
USE_CUSTOM_IDS = os.environ.get("USE_CUSTOM_IDS", "false").lower() == "true"
OFFER_IDS = os.environ.get("OFFER_IDS", "")
REQUEST_IDS = os.environ.get("REQUEST_IDS", "")
REQUEST_TAGS = [t.strip().lower() for t in os.environ.get("REQUEST_TAGS", "any").split(",")]
USE_RANDOM = os.environ.get("USE_RANDOM", "false").lower() == "true"
MIN_VALUE = int(os.environ.get("MIN_VALUE", "0"))
CREATE_FAIR_TRADE = os.environ.get("CREATE_FAIR_TRADE", "false").lower() == "true"

CHECK_ONLY_UGC = False

def log_to_discord(message, target_url=None):
    """Sends a simple, non-embed text message to Discord."""
    target_url = target_url or LOG_WEBHOOK_URL
    if not target_url: return
    try:
        requests.post(target_url, json={"content": str(message)}, timeout=10)
    except: pass

def safe_get_json(url, timeout=10, proxy=None):
    """Safely fetches JSON and ensures it is a dictionary, not a string."""
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=timeout, proxies=proxy)
        # Handle cases where Roblox returns a non-200 status (like 429 or 403)
        if res.status_code != 200:
            log_to_discord(f"⚠️ API Error {res.status_code} for URL: {url}")
            return {}
        return res.json()
        log_to_discord(f"API Warning: Expected dict but got {type(data)} from {url}")
        return {}
    except Exception as e:
        log_to_discord(f"Request failed for {url}: {e}")
        return {}

def get_proxy():
    if not WEBSHARE_URL: return None
    try:
        res = requests.get(WEBSHARE_URL, timeout=10)
        proxy = random.choice(res.text.strip().splitlines()).split(':')
        formatted = f"http://{proxy[2]}:{proxy[3]}@{proxy[0]}:{proxy[1]}"
        return {"http": formatted, "https": formatted}
    except: return None

def get_outbid_status(my_assets, item_details):
    outbid_items = []
    ugc_list = []

    # 1. Filter for potential UGC (ID > 1B) and sort by price
    for asset_id in my_assets.keys():
        asset_str = str(asset_id)
        if asset_str in item_details:
            if not CHECK_ONLY_UGC or int(asset_id) > 12000000000:
                price = item_details[asset_str][2] or 0
                ugc_list.append({"id": asset_id, "name": item_details[asset_str][0], "price": price})

    ugc_list.sort(key=lambda x: x['price'], reverse=True)
    top_ugc = ugc_list[:20] # Limit to top 20 expensive items

    if not top_ugc:
        log_to_discord("✅ No UGC items found to check.")
        return []

    # Preview to Discord
    preview_names = [f"- {i['name']} ({i['price']} R$)" for i in top_ugc]
    log_to_discord("📋 **Checking Outbid Status for:**\n" + "\n".join(preview_names))

    for item in top_ugc:
        asset_id = item['id']
        name = item['name']
        proxy = get_proxy()

        # Step A: Get Collectible ID and Creator
        m_url = f"https://catalog.roblox.com/v1/catalog/items/{asset_id}/details?itemType=Asset"
        m_data = safe_get_json(m_url, proxy=proxy)
        
        # SKIP IF CREATED BY ROBLOX (ID 1)
        if CHECK_ONLY_UGC and m_data.get('creatorTargetId') == 1:
            continue

        collect_id = m_data.get('collectibleItemId')
        market_floor = m_data.get('lowestResalePrice') or m_data.get('price') or 0
        
        if not collect_id or market_floor == 0:
            time.sleep(1)
            continue

        # Step B: Check Resellers
        r_url = f"https://apis.roblox.com/marketplace-sales/v1/item/{collect_id}/resellers?limit=100"
        r_data = safe_get_json(r_url, proxy=proxy)
        reseller_list = r_data.get('data', [])

        # Find your own listing
        my_listings = [r for r in reseller_list if str(r.get('seller', {}).get('sellerId')) == str(PLAYER_ID)]
        
        if my_listings:
            my_min = min(l['price'] for l in my_listings)
            if market_floor < my_min:
                outbid_items.append({
                    "name": name,
                    "your_price": my_min,
                    "current_floor": market_floor,
                    "diff": my_min - market_floor
                })
        
        time.sleep(0.5) # Anti-rate-limit delay

    # Summary
    log_to_discord(f"🏁 Checked {len(top_ugc)} items. Found {len(outbid_items)} outbids.")
    return outbid_items

def send_outbid_alert(items):
    if not OUTBID_WEBHOOK_URL or not items: return
    fields = []
    for item in items:
        fields.append({
            "name": f"🚨 {item['name']}",
            "value": f"**Your Price:** {item['your_price']} R$\n**Lowest Price:** {item['current_floor']} R$\n**Gap:** -{item['diff']} R$",
            "inline": True
        })
    payload = {
        "username": "Outbid Tracker",
        "embeds": [{
            "title": "⚠️ Outbid on Limiteds!",
            "color": 0xffcc00,
            "fields": fields,
            "footer": {"text": f"OxK | Checked: {datetime.now().strftime('%I:%M %p')}"}
        }]
    }
    requests.post(OUTBID_WEBHOOK_URL, json=payload)



def get_player_metadata():
    username, headshot, display_name = "Unknown", "https://www.roblox.com/images/tree_small.png", "Unknown"
    try:
        user_res = requests.get(f"https://users.roblox.com/v1/users/{PLAYER_ID}").json()
        username = user_res.get("name", "Unknown")
        display_name = user_res.get("displayName", "Unknown")
        thumb_url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={PLAYER_ID}&size=420x420&format=Png&isCircular=false"
        thumb_res = requests.get(thumb_url).json()
        if "data" in thumb_res and len(thumb_res["data"]) > 0:
            headshot = thumb_res["data"][0]["imageUrl"]
    except: pass
    return username, headshot, display_name

def get_item_metadata(target_ids):
    try:
        res = requests.get("https://api.rolimons.com/items/v1/itemdetails", timeout=10).json()
        items_map = res.get("items", {})
        results = []
        for tid in target_ids:
            data = items_map.get(str(tid))
            if data:
                val = data[3] if (len(data) > 3 and data[3] != -1) else data[2]
                results.append({"name": data[0], "value": val, "id": int(tid)})
            else:
                results.append({"name": f"Unknown ({tid})", "value": 0, "id": int(tid)})
        return results
    except: return []

def send_visual_webhook(offering_metadata, requesting_ids, status_msg, success=True):
    if not WEBHOOK_URL: return
    username, headshot, display_name = get_player_metadata()
    requesting_metadata = get_item_metadata(requesting_ids) if requesting_ids else []
    
    offer_text = "\n".join([f"• **{i['name']}** (`R${i['value']:,}`)" for i in offering_metadata])
    request_text = "\n".join([f"• **{i['name']}** (`R${i['value']:,}`)" for i in requesting_metadata]) #if requesting_metadata else "• *Any / Offers*"
    tags_text = ", ".join([f"`{t.upper()}`" for t in REQUEST_TAGS])
    
    total_off = sum(i['value'] for i in offering_metadata)
    total_req = sum(i['value'] for i in requesting_metadata) if requesting_metadata else 0
    
    embed = {
        "title": f"💎 {display_name} (@{username})",
        "url": f"https://www.rolimons.com/player/{PLAYER_ID}",
        "color": 0x00ff95 if success else 0xff3333,
        "thumbnail": {"url": headshot},
        "fields": [
            {"name": f"📤 Offering (Total: R${total_off:,})", "value": offer_text or "Empty", "inline": False},
            {"name": f"📥 Requesting (Total: R${total_req:,})", "value": f"{request_text}\n🏷️ Tags: {tags_text}", "inline": False},
            {"name": "📢 Status", "value": f"**{status_msg}**", "inline": False}
        ],
        "footer": {"text": f"OxK | {datetime.now().strftime('%I:%M %p')}"}
    }
    requests.post(WEBHOOK_URL, json={"embeds": [embed], "username": "OxK's Trade Ad Bot"})

def main():
    log_to_discord(f"🚀 Bot Sequence Started at {datetime.now().strftime('%H:%M:%S')}")

    # 1. FETCH INVENTORY FROM BOTH SOURCES
    # Classic Limiteds
    inv_data = safe_get_json(f"https://api.rolimons.com/players/v1/playerassets/{PLAYER_ID}", timeout=15)
    standard_assets = inv_data.get('playerAssets') or inv_data.get('assets') or {}

    # UGC Limiteds
    ugc_url = f"https://inventory.roblox.com/v1/users/{PLAYER_ID}/assets/collectibles?limit=100"
    ugc_data = safe_get_json(ugc_url, timeout=15, proxy=get_proxy())
    raw_ugc_list = ugc_data.get('data', [])
    ugc_assets = {str(item['assetId']): [item['userAssetId']] for item in raw_ugc_list}

    # MERGE INVENTORIES
    my_assets = {**standard_assets, **ugc_assets}
    item_details = safe_get_json("https://api.rolimons.com/items/v1/itemdetails").get('items', {})

    if not my_assets:
        log_to_discord("❌ Error: Inventory empty or private.")
        return

    # 2. TRADE AD POSTING
    if USE_CUSTOM_IDS:
        offering_metadata = get_item_metadata([int(i.strip()) for i in OFFER_IDS.split(",") if i.strip()])
    else:
        inventory_list = []
        for asset_id, instances in my_assets.items():
            details = item_details.get(str(asset_id))
            if details:
                # Get the value (Price or RAP)
                val = details[3] if (len(details) > 3 and details[3] != -1) else details[2]
                
                # Check if it meets the minimum value requirement
                if val >= MIN_VALUE:
                    num_copies = len(instances) if isinstance(instances, list) else 1
                    for _ in range(num_copies):
                        inventory_list.append({'id': int(asset_id), 'name': details[0], 'value': val})

        if USE_RANDOM:
            # Shuffle the qualified items and pick 4
            random.shuffle(inventory_list)
            offering_metadata = inventory_list[:4]
        else:
            # Default: Pick top 4 by value
            offering_metadata = sorted(inventory_list, key=lambda x: x['value'], reverse=True)[:4]

    if offering_metadata:
        offer_ids = [i['id'] for i in offering_metadata]
        request_ids = [int(i.strip()) for i in REQUEST_IDS.split(",") if i.strip()]

        # === FAIR TRADE LOGIC ===
        if CREATE_FAIR_TRADE and total_offer_value > 0:
            fair_items = []
            # Looks for items within a +/- 5% margin of your total offer
            min_target = total_offer_value * 0.95
            max_target = total_offer_value * 1.05

            for item_id, details in item_details.items():
                val = details[3] if (len(details) > 3 and details[3] != -1) else details[2]
                # Don't request items we are currently offering
                if int(item_id) in offer_ids: continue
                
                # If the item value falls within our fair trade margin, add it to potential requests
                if min_target <= val <= max_target:
                    fair_items.append(int(item_id))

            if fair_items:
                random.shuffle(fair_items)
                request_ids = fair_items[:4] # Pick up to 4 random fair items to request
                log_to_discord(f"⚖️ Auto Fair Trade: Found items matching ~R${total_offer_value:,}")
            else:
                log_to_discord(f"⚠️ Auto Fair Trade: Could not find items matching R${total_offer_value:,}. Using default requests.")


        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json', 'Origin': 'https://www.rolimons.com', 'Referer': 'https://www.rolimons.com/tradeads'})
        session.cookies.set('_RoliVerification', COOKIE, domain='.rolimons.com')
        
        payload = {"player_id": int(PLAYER_ID), "offer_item_ids": offer_ids, "request_item_ids": request_ids, "request_tags": REQUEST_TAGS}
        posted = False
        for attempt in range(3):
            proxy = get_proxy()
            try:
                res = session.post("https://api.rolimons.com/tradeads/v1/createad", json=payload, proxies=proxy, timeout=15)
                if res.status_code in [200, 201]:
                    send_visual_webhook(offering_metadata, request_ids, "✅ Ad posted successfully!")
                    posted = True
                    break
                if "cooldown" in res.text.lower():
                    send_visual_webhook(offering_metadata, request_ids, "⏳ Cooldown active.", False)
                    posted = True
                    break
            except: pass
            time.sleep(5)
        if not posted:
            send_visual_webhook(offering_metadata, request_ids, "❌ Failed to post ad.", False)

    # 3. OUTBID MONITORING
    if MONITOR_OUTBID:
        outbid_list = get_outbid_status(my_assets, item_details)
        if outbid_list:
            send_outbid_alert(outbid_list)
        else:
            log_to_discord("✅ No items currently outbid.")

if __name__ == "__main__":
    main()
