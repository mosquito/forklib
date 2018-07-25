import errno
import os
import signal
import logging
import multiprocessing
import random
import warnings

from binascii import hexlify


try:
    from gc import freeze, unfreeze
except ImportError:
    warnings.warn('Python GC can not be frozen. '
                  'Memory will not be shared effectively.')


    def freeze():
        pass


    def unfreeze():
        pass


DEFAULT_SIGNALS = frozenset({
    signal.SIGTERM,
    signal.SIGINT,
    signal.SIGQUIT,
    signal.SIGALRM,
    signal.SIGUSR1,
    signal.SIGUSR2,
})

INTERRUPT_SIGNALS = frozenset({
    signal.SIGTERM,
    signal.SIGINT
})



TASK_ID = None



def fork(num_processes, entrypoint, pass_signals=DEFAULT_SIGNALS,
         auto_restart=False, callback=None, shutdown_callback=None):

    log = logging.getLogger(__name__)

    if num_processes is None or num_processes <= 0:
        num_processes = multiprocessing.cpu_count()

    log.debug("Starting %d processes", num_processes)
    children = {}
    interrupt = False

    def signal_to_children(sig, frame):
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

    # main process
    for sig in pass_signals:
        signal.signal(sig, signal_to_children)

    while children:
        try:
            pid, status = os.wait()
        except OSError as e:
            err_no = None

            if hasattr(e, 'errno'):
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
                os.WTERMSIG(status)
            )

        elif os.WEXITSTATUS(status) != 0:
            log.warning(
                "Child with PID: %d Number: %d exited with status %d.",
                pid,
                process_id,
                os.WEXITSTATUS(status)
            )
        else:
            log.debug(
                "Child with PID: %d Number: %d exited normally",
                pid, process_id
            )

        if auto_restart and not interrupt:
            start(process_id)


def get_id():
    """Returns the current task id"""
    global TASK_ID
    return TASK_ID
