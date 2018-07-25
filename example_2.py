from time import sleep

from forklib import fork_map, fork
import logging


logging.basicConfig(level=logging.INFO)


def map_func(x):
    return x + 1


def main():
    for item in fork_map(map_func, range(20000), workers=5):
        print(item)

    fork(2, lambda: sleep(1), auto_restart=True)


if __name__ == '__main__':
    main()
