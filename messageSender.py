import asyncio
import aiohttp

telegram_token = "6519297911:AAH-cGmGvF6wh0Gb-55sBBhB0Hi8W6j3U0c"
chat_id = "1188913547"
discord_webhook_url = "https://discord.com/api/webhooks/1242331878053253142/uK3gJYARjx_Js8zN0n5LZa7vXzSziQGDGxGVxyYX-QDMZUUbGXeQjHGi9zoD9OUTnhP6"  
    

async def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": chat_id, "text": message}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as response:
            try:
                return await response.json()
            except aiohttp.ContentTypeError:
                return True


async def send_discord_message(message: str, max_retries: int = 3):
    data = {"content": message}
    retries = 0
    async with aiohttp.ClientSession() as session:
        while retries <= max_retries:
            try:
                async with session.post(discord_webhook_url, json=data) as resp:
                    if resp.status == 204:
                        return True
                    if resp.status == 429:
                        retry_after = float(resp.headers.get("Retry-After", 5))
                        print(f"[Discord Rate Limit] retry in {retry_after}s")
                        await asyncio.sleep(retry_after)
                        retries += 1
                        continue
                    if resp.status >= 400:
                        txt = await resp.text()
                        print(f"[Discord Error] {resp.status}: {txt}")
                        return False
                    try:
                        return await resp.json()
                    except aiohttp.ContentTypeError:
                        return True
            except aiohttp.ClientError as e:
                print(f"[Discord Network Error] {e}")
                await asyncio.sleep(2)
                retries += 1
    print(f"[Discord Error] Failed after {max_retries} retries.")
    return False


async def send_message_notify(message: str):
    await asyncio.gather(
        send_telegram_message(message),
        send_discord_message(message),
    )
