import asyncio
import logging
import os
import time
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


def thread_callback():
    sleep(10)
    print("thread callback finished")


async def async_callback():
    await asyncio.sleep(5)
    print("Async callback finished")


def main():
    print("Master proccess has PID: {0}".format(os.getpid()))
    forklib.fork(
        4, run,
        async_callback=async_callback,
        thread_callback=thread_callback,
        wait_thread_callback=True,
    )


if __name__ == "__main__":
    main()
