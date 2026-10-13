"""Independent execution process: uv run --locked python -m aigc.worker_main."""

import asyncio
import logging
import signal
import time

from . import broker
from .comfy import Comfy
from .config import load
from .delivery import Delivery
from .store import Store
from .worker import Worker


async def serve(config):
    store = Store(config["AIGC_DATA_DIR"])
    mode = config.get("AIGC_EXECUTION_MODE", "local")
    client = Comfy(config["AIGC_COMFY_URL"])
    worker = None
    tasks = []
    try:
        worker = Worker(store, client, mode=mode, gpu_lock=config["AIGC_GPU_LOCK"])
        Delivery(store).bind_mode(mode)
        tasks.append(asyncio.create_task(worker.run()))

        async def heartbeat():
            while True:
                store.put("runtime", {"at": time.time(), "mode": mode}, "worker", replace=True)
                await asyncio.sleep(3)

        tasks.append(asyncio.create_task(heartbeat()))
        if mode == "rabbitmq":
            tasks.append(asyncio.create_task(broker.run(store, config)))
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        tasks.append(asyncio.create_task(stop.wait()))
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            if worker:
                try:
                    store.put("runtime", {"at": 0, "mode": mode}, "worker", replace=True)
                finally:
                    worker.close()
        finally:
            await client.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # Transport internals may include AMQP connection URLs. Our adapter emits
    # sanitized connection state and correlation IDs instead.
    logging.getLogger("aio_pika").setLevel(logging.CRITICAL)
    logging.getLogger("aiormq").setLevel(logging.CRITICAL)
    asyncio.run(serve(load()))


if __name__ == "__main__":
    main()
