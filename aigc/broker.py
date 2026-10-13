"""AMQP transport for the durable outbox/inbox; no generation logic."""

import asyncio
import json
import logging
import time

from .delivery import Delivery

log = logging.getLogger(__name__)


async def publish_pending(ledger, publish):
    """A lost confirm can duplicate delivery; it cannot lose the database intent."""
    for entry in ledger.pending():
        try:
            await publish(entry)
        except Exception as error:
            ledger.publish_failed(entry["id"], type(error).__name__)
            raise
        ledger.published(entry["id"])
        log.info(
            "outbox_confirmed request_id=%s job_id=%s message_id=%s kind=%s",
            entry["request_id"],
            entry["job_id"],
            entry["id"],
            entry["kind"],
        )


async def receive(ledger, message):
    try:
        payload = json.loads(message.body)
        if not isinstance(payload, dict) or set(payload) != {"job_id", "generation"}:
            raise ValueError("Invalid delivery envelope")
        if (
            not isinstance(payload["job_id"], str)
            or type(payload["generation"]) is not int
            or payload["generation"] < 0
        ):
            raise ValueError("Invalid delivery identifiers")
    except (ValueError, TypeError):
        await message.reject(requeue=False)
        return
    # Bound processing time well below the broker ACK timeout. No network/GPU
    # work occurs here. A database outage exhausts retries into the DLQ.
    for attempt in range(3):
        try:
            await asyncio.to_thread(ledger.accept, payload["job_id"], payload["generation"])
            break
        except ValueError:
            await message.reject(requeue=False)
            return
        except Exception:
            if attempt == 2:
                await message.reject(requeue=False)
                return
            await asyncio.sleep(2**attempt)
    await message.ack()
    log.info(
        "inbox_committed request_id=%s job_id=%s message_id=%s",
        message.correlation_id,
        payload["job_id"],
        message.message_id,
    )


async def topology(channel, name):
    import aio_pika

    dead = await channel.declare_exchange(
        name + ".dead", aio_pika.ExchangeType.DIRECT, durable=True
    )
    dlq = await channel.declare_queue(
        name + ".dead", durable=True, arguments={"x-queue-type": "quorum"}
    )
    await dlq.bind(dead, routing_key=name)
    exchange = await channel.declare_exchange(name, aio_pika.ExchangeType.DIRECT, durable=True)
    queue = await channel.declare_queue(
        name,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-single-active-consumer": True,
            "x-delivery-limit": 3,
            "x-dead-letter-exchange": name + ".dead",
            "x-dead-letter-routing-key": name,
            "x-dead-letter-strategy": "at-least-once",
            "x-overflow": "reject-publish",
        },
    )
    await queue.bind(exchange, routing_key=name)
    return exchange, dead, queue


async def run(store, config):
    import aio_pika

    ledger = Delivery(store)
    name = config.get("AIGC_RABBITMQ_QUEUE", "caster.gpu0")
    while True:
        try:
            async with await aio_pika.connect(
                config["AIGC_RABBITMQ_URL"], timeout=10
            ) as connection:
                channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
                await channel.set_qos(prefetch_count=1)
                exchange, dead, queue = await topology(channel, name)

                async def publish(entry):
                    message = aio_pika.Message(
                        json.dumps(
                            {"job_id": entry["job_id"], "generation": entry["generation"]}
                        ).encode(),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        content_type="application/json",
                        message_id=entry["id"],
                        correlation_id=entry["request_id"],
                    )
                    await (dead if entry["kind"] == "dead" else exchange).publish(
                        message, routing_key=name, mandatory=True, timeout=10
                    )

                async def relay():
                    while True:
                        await publish_pending(ledger, publish)
                        store.put(
                            "runtime",
                            {"connected": True, "at": time.time()},
                            "broker",
                            replace=True,
                        )
                        await asyncio.sleep(1)

                async with asyncio.TaskGroup() as tasks:
                    tasks.create_task(relay())
                    async with queue.iterator(no_ack=False) as messages:
                        async for message in messages:
                            await receive(ledger, message)
                    raise ConnectionError("Consumer stopped")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Never log a connection exception's repr: it may contain credentials.
            log.warning(
                "broker_unavailable error_type=%s; durable outbox retained", type(error).__name__
            )
            store.put("runtime", {"connected": False, "at": time.time()}, "broker", replace=True)
            await asyncio.sleep(2)
