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
    # This is only test, in the project html resourse will loaded by fronted-server. Ant this
    # fronted-server will `knokcs` to api in this backend server.
    return FileResponse("index.html")


async def event_generator(request: Request, session_id: str):
    """Listen for Redis pub/sub messages and yield SSE events"""
    pubsub = redis_client.pubsub()

    # subscribe to publisher with game session_id
    await pubsub.subscribe(str(session_id))

    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                # await new message from publisher, generator
                # will stoped unless new message will comed.
                message = await pubsub.get_message(timeout=None)

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


@app.get("/stream/{session_id}")
async def message_stream(request: Request, session_id: uuid.UUID):
    # TODO: read about this func and compare with StreamingResponse by fastapi.responses
    # Read about this: https://medium.com/@nandagopal05/server-sent-events-with-python-fastapi-f1960e0c8e4b
    return EventSourceResponse(
        event_generator(
            request,
            str(session_id),
        )
    )


@app.post("/publish")
async def publish_message(message: str, session_id: str):
    """
    Publish message in the redis pub, thats declared by session_id

    :param message: message to publish
    :param session_id: name of publish channel
    """
    await redis_client.publish(str(session_id), message)

    return {
        "success": True,
    }


if __name__ == "__main__":
    uvicorn.run("app:app", reload=True)
