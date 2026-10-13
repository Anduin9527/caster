"""Real RabbitMQ tests, opt-in: AIGC_TEST_AMQP_URL=... uv run pytest ..."""

import asyncio
import json
import os
import uuid

import pytest

from aigc import broker
from aigc.delivery import Delivery
from aigc.store import Store

AMQP_URL = os.environ.get("AIGC_TEST_AMQP_URL")
pytestmark = pytest.mark.skipif(not AMQP_URL, reason="isolated RabbitMQ not configured")


def test_real_confirm_duplicate_ack_and_dead_letter(tmp_path):
    import aio_pika

    async def scenario():
        name = "caster.test." + uuid.uuid4().hex
        store = Store(tmp_path)
        ledger = Delivery(store)
        job = store.create_job({"idempotency_key": "real-broker"})
        async with await aio_pika.connect(AMQP_URL) as connection:
            channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
            await channel.set_qos(prefetch_count=1)
            exchange, dead, queue = await broker.topology(channel, name)
            dlq = await channel.get_queue(name + ".dead")
            try:

                async def publish(entry):
                    await exchange.publish(
                        aio_pika.Message(
                            json.dumps(
                                {"job_id": entry["job_id"], "generation": entry["generation"]}
                            ).encode(),
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            message_id=entry["id"],
                            correlation_id=entry["request_id"],
                        ),
                        routing_key=name,
                        mandatory=True,
                    )

                await broker.publish_pending(ledger, publish)
                # Duplicate the already confirmed message to model lost publisher confirm.
                with store.connect() as db:
                    entry = dict(db.execute("SELECT * FROM job_outbox").fetchone())
                await publish(entry)
                # Poison message gets rejected without requeue and reaches durable DLQ.
                await exchange.publish(
                    aio_pika.Message(
                        b"invalid-json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                    ),
                    routing_key=name,
                )
                async with queue.iterator(no_ack=False) as messages:
                    for _ in range(3):
                        message = await asyncio.wait_for(anext(messages), 5)
                        await broker.receive(ledger, message)
                assert ledger.info(job["id"])["received"]
                assert store.job(job["id"])["state"] == "queued"
                for _ in range(50):
                    message = await dlq.get(fail=False)
                    if message:
                        assert message.body == b"invalid-json"
                        assert message.headers["x-first-death-reason"] == "rejected"
                        await message.ack()
                        break
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("Dead letter was not delivered")
                assert (await queue.declare()).message_count == 0
            finally:
                await queue.delete(if_unused=False, if_empty=False)
                await dlq.delete(if_unused=False, if_empty=False)
                await exchange.delete(if_unused=False)
                await dead.delete(if_unused=False)

    asyncio.run(scenario())
