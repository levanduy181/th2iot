"""Loopback-only MQTT broker for the local teaching lab."""
import asyncio
import logging
from amqtt.broker import Broker
from settings import CONFIG


async def main():
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{CONFIG['mqtt_port']}"}},
        "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}},
    })
    await broker.start()
    print(f"MQTT ready: 127.0.0.1:{CONFIG['mqtt_port']}", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
