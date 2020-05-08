import os
import pickle
import struct
import typing
from gzip import GzipFile
from tempfile import NamedTemporaryFile

from .forking import freeze, unfreeze


HEADER = struct.Struct(">Q")


def fork_map(
    func, arg_list: typing.Iterable,
    workers: int = 10, tmp_dir=None, gzip=False,
    gzip_level=4,
) -> typing.Generator[None, typing.Any, None]:

    result_files = [
        NamedTemporaryFile(
            mode="wb+",
            delete=False,
            dir=tmp_dir,
            prefix="fork-map-",
            suffix=".results.gz" if gzip else ".results",
        )
        for _ in range(workers)
    ]

    if not isinstance(arg_list, list):
        arg_list = list(arg_list)

    children = set()

    freeze()

    for i in range(workers):
        pid = os.fork()
        if pid:
            children.add(pid)
            continue

        if gzip:
            result_file = GzipFile(
                fileobj=result_files[i], mode="wb", compresslevel=gzip_level,
            )
        else:
            result_file = result_files[i]

        for task in arg_list[i::workers]:
            try:
                res = pickle.dumps((func(task), False))
            except Exception as e:
                res = pickle.dumps((e, True))

            result_file.write(HEADER.pack(len(res)))
            result_file.write(res)

        result_file.flush()
        return exit(0)

    unfreeze()

    while children:
        pid, code = os.wait()
        if code:
            raise RuntimeError(
                "Child process %d exited with code %r", pid, code,
            )

        children.remove(pid)

    for i in range(workers):
        result_files[i].seek(0)

    if gzip:
        result_read_files = [
            GzipFile(fileobj=fp, mode="rb") for fp in result_files
        ]
    else:
        result_read_files = result_files

    try:
        for i in range(len(arg_list)):
            fp = result_read_files[i % workers]
            hdr = fp.read(HEADER.size)
            size = HEADER.unpack(hdr)[0]
            res, exc = pickle.loads(fp.read(size))

            if exc:
                raise exc

            yield res
    finally:
        for fp in result_files:
            os.remove(fp.name)
