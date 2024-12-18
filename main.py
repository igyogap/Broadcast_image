import asyncio
import datetime
import logging
import os
from telegram import Bot
from telegram.error import RetryAfter, TimedOut, NetworkError, TelegramError
from telegram.request import HTTPXRequest
from dbinterface import DBInterface
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TOKEN')  
MAX_RETRY_AFTER = 100  
DELAY_BETWEEN_USERS = 0.5 
NUM_WORKERS = 5  


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

stats = {
    "total_rate_limit_time": 0,
    "total_users_hit": 0,
    "total_workers": 0,
    "unique_chat_ids": set()
}


db = DBInterface()


async def fetch_user_ids(status):
    await db.init_pool()
    sql = "SELECT id, chatid FROM `user_kaleidoskop_new` WHERE status_bc = %s"
    return await db.queries(sql, (status,))

async def update_status(status, user_id):
    sql = "UPDATE `user_kaleidoskop_new` SET status_bc = %s WHERE id = %s"
    await db.commands(sql, (status, user_id))

async def send_image(bot, chat_id, file_id):
    try:
        await bot.send_photo(chat_id=chat_id, photo=file_id)
        stats["total_users_hit"] += 1
        stats["unique_chat_ids"].add(chat_id)
        logger.info(f"Successfully sent image to user {chat_id}")
    except RetryAfter as e:
        retry_after = min(e.retry_after, MAX_RETRY_AFTER)
        stats["total_rate_limit_time"] += retry_after
        logger.warning(f"Rate limit hit for user {chat_id}. Retrying after {retry_after} seconds...")
        await asyncio.sleep(retry_after)
        await send_image(bot, chat_id, file_id)
    except (TimedOut, NetworkError) as e:
        logger.warning(f"Temporary network error for user {chat_id}: {e}. Retrying...")
        await asyncio.sleep(5)
        await send_image(bot, chat_id, file_id)
    except TelegramError as e:
        logger.error(f"Failed to send image to user {chat_id}: {e}")
        await update_status('-1', chat_id)

async def broadcast_worker(bot, file_id, user_ids, semaphore, worker_id):
    logger.info(f"Worker {worker_id} started processing {len(user_ids)} users.")
    stats["total_workers"] += 1
    async with semaphore:
        for user_id, chat_id in user_ids:
            await send_image(bot, chat_id, file_id)
            await update_status('1', user_id)
            await asyncio.sleep(DELAY_BETWEEN_USERS)
    logger.info(f"Worker {worker_id} finished processing.")

async def broadcast_images_concurrently(bot, num_workers=NUM_WORKERS):
    user_ids = [(item['id'], item['chatid']) for item in await fetch_user_ids(status='0')]
    if not user_ids:
        logger.info("No users to broadcast to.")
        return

    logger.info(f"Fetched {len(user_ids)} user IDs for broadcasting.")
    
    first_chat_id = user_ids[0][1]
    image_path = "1.jpg"  
    with open(image_path, 'rb') as image_file:
        message = await bot.send_photo(chat_id=first_chat_id, photo=image_file)
    file_id = message.photo[-1].file_id
    logger.info("Image uploaded successfully. File ID obtained.")

    semaphore = asyncio.Semaphore(num_workers)
    tasks = [
        broadcast_worker(bot, file_id, user_ids[i::num_workers], semaphore, i + 1)
        for i in range(num_workers)
    ]
    await asyncio.gather(*tasks)

async def retry_failed_broadcast(bot, num_workers):
    while True:
        failed_users = await fetch_user_ids(status='-1')
        if not failed_users:
            logger.info("No failed users left to retry.")
            break

        logger.info(f"Retrying for {len(failed_users)} failed users.")
        user_ids = [(item['id'], item['chatid']) for item in failed_users]
        image_path = "2.jpg"  
        with open(image_path, 'rb') as image_file:
            message = await bot.send_photo(chat_id=user_ids[0][1], photo=image_file)
        file_id = message.photo[-1].file_id
        semaphore = asyncio.Semaphore(num_workers)
        tasks = [
            broadcast_worker(bot, file_id, user_ids[i::num_workers], semaphore, i + 1)
            for i in range(num_workers)
        ]
        await asyncio.gather(*tasks)
        await asyncio.sleep(5)

async def main():
    request = HTTPXRequest(
        connection_pool_size=30,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0
    )
    bot = Bot(token=BOT_TOKEN, request=request)

    start_time = datetime.datetime.now()
    logger.info(f"Broadcast started at {start_time}")
    
    await broadcast_images_concurrently(bot, num_workers=NUM_WORKERS)
    await retry_failed_broadcast(bot, num_workers=NUM_WORKERS)

    await db.close_pool()  
    end_time = datetime.datetime.now()

    logger.info(f"Broadcast finished at {end_time}")
    logger.info(f"Total execution time: {end_time - start_time}")
    logger.info(f"Total rate limit time: {stats['total_rate_limit_time']} seconds")
    logger.info(f"Total users processed: {stats['total_users_hit']}")
    logger.info(f"Total workers used: {stats['total_workers']}")
    logger.info(f"Total unique chat IDs: {len(stats['unique_chat_ids'])}")

if __name__ == "__main__":
    asyncio.run(main())
