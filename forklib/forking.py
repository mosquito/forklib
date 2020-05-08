import asyncio
import errno
import logging
import multiprocessing
import os
import random
import signal
import typing
import warnings
from binascii import hexlify
from enum import IntEnum
from sys import exit
from threading import Event, Thread


try:
    from gc import freeze, unfreeze
except ImportError:
    warnings.warn(
        "Python GC can not be frozen. "
        "Memory will not be shared effectively.",
    )


    def freeze():
        pass


    def unfreeze():
        pass


class Signal(IntEnum):
    ITIMER_REAL = 0
    ITIMER_VIRTUAL = 1
    ITIMER_PROF = 2
    NSIG = 32

    SIGABRT = 6
    SIGALRM = 14
    SIGBUS = 10
    SIGCHLD = 20
    SIGCONT = 19
    SIGEMT = 7
    SIGFPE = 8
    SIGHUP = 1
    SIGILL = 4
    SIGINFO = 29
    SIGINT = 2
    SIGIO = 23
    SIGIOT = 6
    SIGKILL = 9
    SIGPIPE = 13
    SIGPROF = 27
    SIGQUIT = 3
    SIGSEGV = 11
    SIGSTOP = 17
    SIGSYS = 12
    SIGTERM = 15
    SIGTRAP = 5
    SIGTSTP = 18
    SIGTTIN = 21
    SIGTTOU = 22
    SIGURG = 16
    SIGUSR1 = 30
    SIGUSR2 = 31
    SIGVTALRM = 26
    SIGWINCH = 28
    SIGXCPU = 24
    SIGXFSZ = 25

    SIG_BLOCK = 1
    SIG_DFL = 0
    SIG_IGN = 1
    SIG_SETMASK = 3
    SIG_UNBLOCK = 2


DEFAULT_SIGNALS = frozenset({
    Signal.SIGTERM,
    Signal.SIGINT,
    Signal.SIGQUIT,
    Signal.SIGALRM,
    Signal.SIGUSR1,
    Signal.SIGUSR2,
})

INTERRUPT_SIGNALS = frozenset({
    Signal.SIGTERM,
    Signal.SIGINT,
})


TASK_ID = None

AsyncCallbackType = typing.Callable[
    [], typing.Coroutine[None, None, typing.Any],
]
CallbackType = typing.Callable[[], typing.Any]
ShutdownCallbackType = typing.Callable[[int], typing.Any]


def fork(
    num_processes, entrypoint,
    pass_signals: typing.AbstractSet[int] = DEFAULT_SIGNALS,
    auto_restart: bool = False,
    callback: CallbackType = None,
    shutdown_callback: ShutdownCallbackType = None,
    async_callback: AsyncCallbackType = None,
    wait_async_callback: bool = True,
):

    log = logging.getLogger(__name__)

    if num_processes is None or num_processes <= 0:
        num_processes = multiprocessing.cpu_count()

    log.debug("Starting %d processes", num_processes)
    children = {}
    interrupt = False

    def signal_to_children(sig: int, frame):
        nonlocal children, interrupt

        if sig in INTERRUPT_SIGNALS:
            if callable(shutdown_callback):
                shutdown_callback(sig)
            interrupt = True

        for pid in children:
            os.kill(pid, sig)

    def start(number):
        freeze()
        pid = os.fork()
        unfreeze()

        if pid:
            children[pid] = number
            return None

        # child process
        seed = int(hexlify(os.urandom(16)), 16)
        random.seed(seed)

        global TASK_ID

        for sig in pass_signals:
            signal.signal(sig, lambda c, *_: exit(c))

        TASK_ID = number

        entrypoint()
        exit(0)

    for i in range(num_processes):
        start(i)

    if callable(callback):
        callback()

    def async_shutdown():
        loop = asyncio.get_event_loop()
        tasks = asyncio.Task.all_tasks(loop=loop)
        for task in tasks:
            if task.done():
                continue
            task.cancel()

    def start_async_callback(
        event_loop: asyncio.AbstractEventLoop,
        coroutine_func, shutdown_event: Event,
    ):
        asyncio.set_event_loop(event_loop)

        try:
            event_loop.run_until_complete(coroutine_func())
            event_loop.run_until_complete(event_loop.shutdown_asyncgens())
            event_loop.close()
        finally:
            shutdown_event.set()

    loop_close_event = None
    loop = None
    if asyncio.iscoroutinefunction(async_callback):
        loop = asyncio.new_event_loop()
        loop_close_event = Event()
        thread = Thread(
            target=start_async_callback,
            args=(loop, async_callback, loop_close_event),
        )
        thread.start()

    # main process
    for sig in pass_signals:
        signal.signal(sig, signal_to_children)

    while children:
        try:
            pid, status = os.wait()
        except OSError as e:
            err_no = None

            if hasattr(e, "errno"):
                err_no = e.errno
            elif e.args:
                err_no = e.args[0]

            if err_no == errno.EINTR:
                continue

            raise

        if pid not in children:
            continue

        process_id = children.pop(pid)

        if os.WIFSIGNALED(status):
            log.warning(
                "Child with PID: %d Number: %d killed by signal %d.",
                pid,
                process_id,
                os.WTERMSIG(status),
            )

        elif os.WEXITSTATUS(status) != 0:
            log.warning(
                "Child with PID: %d Number: %d exited with status %d.",
                pid,
                process_id,
                os.WEXITSTATUS(status),
            )
        else:
            log.debug(
                "Child with PID: %d Number: %d exited normally",
                pid, process_id,
            )

        if auto_restart and not interrupt:
            log.warning("Restarting child PID: %r ID: %r", pid, process_id)
            start(process_id)

    if loop is None or loop.is_closed():
        return

    if not wait_async_callback:
        log.debug("Cancelling all imcompleted async tasks")
        loop.call_soon_threadsafe(async_shutdown)
    else:
        log.debug("Waiting for async_callback: %r", async_callback)

    loop_close_event.wait()


def get_id():
    """Returns the current task id"""
    global TASK_ID
    return TASK_ID
