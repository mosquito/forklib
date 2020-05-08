import asyncio
import logging
import os
from time import sleep

import forklib


logging.basicConfig(level=logging.DEBUG)


def run():
    print(
        "Proceess #{id} has PID: {pid}".format(
            id=forklib.get_id(),
            pid=os.getpid(),
        ),
    )
    sleep(1)


async def amain():
    await asyncio.sleep(5)
    print("Async callback finished")


def main():
    print("Master proccess has PID: {0}".format(os.getpid()))
    forklib.fork(4, run, async_callback=amain)


if __name__ == "__main__":
    main()
