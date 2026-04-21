import asyncio
from client import send_to_api
from config import logger, HEARTBEAT_INTERVAL, MAX_RETRIES_LIMIT

async def background_worker(queue: asyncio.Queue):
    """
    Serial Worker with Fixed Heartbeat.
    - Processes 1 item at a time.
    - Waits FIXED_INTERVAL seconds between every attempt.
    - Retries same item up to MAX_RETRIES before dropping.
    """
    logger.info(f"🔧 Worker Started (Heartbeat: {HEARTBEAT_INTERVAL}s | Max Retries: {MAX_RETRIES_LIMIT})")
    
    while True:
        # 1. Pull Job (Waits here if queue is empty)
        payload = await queue.get()
        message_id = payload.get('message_id', 'unknown')
        
        retry_count = 0
        success = False

        # 2. Processing Loop (The "Jammed Gun" logic)
        while not success:
            # Try to send
            success = await send_to_api(payload)

            if success:
                # Great! We are done with this item.
                break
            
            # Failed? Check if we should retry.
            retry_count += 1
            if retry_count >= MAX_RETRIES_LIMIT:
                logger.error(f"💀 DEAD LETTER: Dropping msg #{message_id} after {retry_count} failures.")
                break # Break inner loop, effectively dropping the item
            
            # Log Retry
            logger.warning(f"♻️ Retry {retry_count}/{MAX_RETRIES_LIMIT} for msg #{message_id} in {HEARTBEAT_INTERVAL}s...")
            
            # WAIT before retrying (The Heartbeat)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

        # 3. Cleanup & Pace
        queue.task_done()
        
        # Even on success, we wait the heartbeat interval to ensure steady pacing
        # (Remove this 'if' check if you want instant processing on success, 
        # but you asked for "1 post per 30 seconds" strictly)
        if success:
            logger.info(f"💤 Resting for {HEARTBEAT_INTERVAL}s...")
            await asyncio.sleep(HEARTBEAT_INTERVAL)