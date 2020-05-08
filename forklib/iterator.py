import pickle
import struct
from contextlib import ExitStack
from tempfile import NamedTemporaryFile

from .forking import fork, get_id


def skip(iterable, skip, shift):
    for idx, item in enumerate(iterable):
        if idx % skip != shift:
            continue
        yield item


_HEADER = struct.Struct(">Q")
_HEADER_PLACEHOLDER = b"\x00" * _HEADER.size


def _run(func, iterable, number_processes, fp):
    fp.write(_HEADER_PLACEHOLDER)

    count = 0
    for item in skip(iterable, number_processes, get_id()):
        pickle.dump(func(item), fp)
        count += 1

    fp.seek(0)
    fp.write()


def fork_map(func, iterable, workers: int = 10, tmp_dir=None):
    with ExitStack() as stack:
        result_files = {
            fid: stack.enter_context(
                NamedTemporaryFile(
                    delete=False, dir=tmp_dir,
                ),
            ) for fid in range(workers)
        }

        fork(
            workers, lambda: _run(
                func,
                iterable,
                workers,
                result_files[get_id()].file,
            ),
        )

        for fp in result_files.values():
            fp.delete = True
            fp.seek(0)

        sizes = {
            fid: _HEADER.unpack(fp.read(_HEADER.size))[0]
            for fid, fp in result_files.items()
        }

        while any(sizes.values()):
            for fid in range(workers):
                if not sizes[fid]:
                     continue

                yield pickle.load(result_files[fid])
                sizes[fid] -= 1
