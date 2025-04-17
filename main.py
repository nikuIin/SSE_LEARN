import asyncio
import datetime
import json
import uuid

import redis.asyncio as redis
import uvicorn
from fastapi import FastAPI, Request
from loguru import logger
from sse_starlette.sse import EventSourceResponse
from starlette.responses import FileResponse

app = FastAPI()

# Redis connection configuration
REDIS_URL = "redis://localhost:6379"
CHANNEL_NAME = "messages"

# Initialize Redis client
redis_client = redis.from_url(REDIS_URL)


@app.on_event("shutdown")
async def shutdown_event():
    if redis_client:
        await redis_client.close()


@app.get("/")
async def read_index():
    return FileResponse("index.html")


async def event_generator(request: Request, session_id: str):
    """Listen for Redis pub/sub messages and yield SSE events"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(str(session_id))

    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                message = await pubsub.get_message(timeout=10000000)
                logger.debug(message["data"])
                if message and message.get("type") == "message":
                    yield {
                        "event": "new_message",
                        "retry": 15000,  # Retry timeout in milliseconds
                        "data": message["data"].decode("UTF-8"),
                        "id": str(uuid.uuid4()),
                    }
            except asyncio.CancelledError:
                break

    finally:
        await pubsub.unsubscribe(str(session_id))
        await pubsub.close()


@app.get("/stream")
async def message_stream(
    request: Request, session_id: str = "72403149-969a-456c-a4c9-c672f3540d4c"
):
    return EventSourceResponse(
        event_generator(request, session_id)
    )  # TODO: read about this func


@app.post("/publish")
async def publish_message(
    message: str, session_id: str = "72403149-969a-456c-a4c9-c672f3540d4c"
):
    format_message = {
        "event": "new_message",
        "retry": 15000,  # Retry timeout in milliseconds
        "data": message,
        "id": str(uuid.uuid4()),
    }
    await redis_client.publish(str(session_id), message)
    return format_message


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
