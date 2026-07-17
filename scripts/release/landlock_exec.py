#!/usr/bin/env python3
"""Execute one command with filesystem writes confined to explicit directories."""

from __future__ import annotations

import argparse
import array
import ctypes
import errno
import ipaddress
import os
import select
import signal
import socket
import stat
import struct
import sys
from pathlib import Path
from typing import Sequence


SYS_LANDLOCK_CREATE_RULESET = 444
SYS_LANDLOCK_ADD_RULE = 445
SYS_LANDLOCK_RESTRICT_SELF = 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38
PR_SET_PDEATHSIG = 1

LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1
LANDLOCK_ACCESS_FS_REMOVE_DIR = 1 << 4
LANDLOCK_ACCESS_FS_REMOVE_FILE = 1 << 5
LANDLOCK_ACCESS_FS_MAKE_CHAR = 1 << 6
LANDLOCK_ACCESS_FS_MAKE_DIR = 1 << 7
LANDLOCK_ACCESS_FS_MAKE_REG = 1 << 8
LANDLOCK_ACCESS_FS_MAKE_SOCK = 1 << 9
LANDLOCK_ACCESS_FS_MAKE_FIFO = 1 << 10
LANDLOCK_ACCESS_FS_MAKE_BLOCK = 1 << 11
LANDLOCK_ACCESS_FS_MAKE_SYM = 1 << 12
LANDLOCK_ACCESS_FS_REFER = 1 << 13
LANDLOCK_ACCESS_FS_TRUNCATE = 1 << 14
WRITE_ACCESS = (
    LANDLOCK_ACCESS_FS_WRITE_FILE
    | LANDLOCK_ACCESS_FS_REMOVE_DIR
    | LANDLOCK_ACCESS_FS_REMOVE_FILE
    | LANDLOCK_ACCESS_FS_MAKE_CHAR
    | LANDLOCK_ACCESS_FS_MAKE_DIR
    | LANDLOCK_ACCESS_FS_MAKE_REG
    | LANDLOCK_ACCESS_FS_MAKE_SOCK
    | LANDLOCK_ACCESS_FS_MAKE_FIFO
    | LANDLOCK_ACCESS_FS_MAKE_BLOCK
    | LANDLOCK_ACCESS_FS_MAKE_SYM
    | LANDLOCK_ACCESS_FS_REFER
    | LANDLOCK_ACCESS_FS_TRUNCATE
)

SCMP_ACT_ALLOW = 0x7FFF0000
SCMP_ACT_ERRNO = 0x00050000
SCMP_ACT_NOTIFY = 0x7FC00000
SCMP_CMP_EQ = 4
SCMP_CMP_MASKED_EQ = 7
SOCK_TYPE_MASK = 0xF
MSG_FASTOPEN = getattr(socket, "MSG_FASTOPEN", 0x20000000)
SYS_PIDFD_GETFD = 438


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
        ("reserved", ctypes.c_uint32),
    ]


class SeccompArgCompare(ctypes.Structure):
    _fields_ = [
        ("arg", ctypes.c_uint),
        ("op", ctypes.c_int),
        ("datum_a", ctypes.c_uint64),
        ("datum_b", ctypes.c_uint64),
    ]


class SeccompData(ctypes.Structure):
    _fields_ = [
        ("nr", ctypes.c_int),
        ("arch", ctypes.c_uint32),
        ("instruction_pointer", ctypes.c_uint64),
        ("args", ctypes.c_uint64 * 6),
    ]


class SeccompNotification(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint64),
        ("pid", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("data", SeccompData),
    ]


class SeccompNotificationResponse(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint64),
        ("val", ctypes.c_int64),
        ("error", ctypes.c_int32),
        ("flags", ctypes.c_uint32),
    ]


class IOVec(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("length", ctypes.c_size_t)]


def _syscall(libc: ctypes.CDLL, number: int, *arguments: object) -> int:
    result = int(libc.syscall(number, *arguments))
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return result


def _resolve_directory(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError(f"write allowance must be absolute: {path}")
    resolved = candidate.resolve(strict=True)
    metadata = resolved.stat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"write allowance must be a directory: {resolved}")
    return resolved


def _resolve_seccomp_library(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError("libseccomp path must be absolute")
    resolved = candidate.resolve(strict=True)
    metadata = resolved.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & 0o022
    ):
        raise ValueError(
            f"libseccomp must be a root-owned, non-writable regular file: {resolved}"
        )
    return resolved


def enforce_write_isolation(allowed_roots: Sequence[Path]) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    abi = _syscall(
        libc,
        SYS_LANDLOCK_CREATE_RULESET,
        ctypes.c_void_p(),
        ctypes.c_size_t(0),
        ctypes.c_uint32(LANDLOCK_CREATE_RULESET_VERSION),
    )
    if abi < 3:
        raise RuntimeError(f"Landlock ABI {abi} cannot enforce truncate/refer isolation")
    ruleset = RulesetAttr(handled_access_fs=WRITE_ACCESS)
    ruleset_fd = _syscall(
        libc,
        SYS_LANDLOCK_CREATE_RULESET,
        ctypes.byref(ruleset),
        ctypes.sizeof(ruleset),
        ctypes.c_uint32(0),
    )
    try:
        for root in sorted(set(allowed_roots), key=os.fspath):
            path_fd = os.open(root, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathBeneathAttr(
                    allowed_access=WRITE_ACCESS,
                    parent_fd=path_fd,
                    reserved=0,
                )
                _syscall(
                    libc,
                    SYS_LANDLOCK_ADD_RULE,
                    ruleset_fd,
                    LANDLOCK_RULE_PATH_BENEATH,
                    ctypes.byref(rule),
                    ctypes.c_uint32(0),
                )
            finally:
                os.close(path_fd)
        if int(libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        _syscall(libc, SYS_LANDLOCK_RESTRICT_SELF, ruleset_fd, ctypes.c_uint32(0))
    finally:
        os.close(ruleset_fd)
    return abi


def install_network_seccomp(library_path: str) -> tuple[int, str]:
    """Install fail-closed socket rules and return the connect-notify listener."""

    if not library_path:
        raise RuntimeError("libseccomp is unavailable")
    library = ctypes.CDLL(library_path, use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    library.seccomp_release.restype = None
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(SeccompArgCompare),
    ]
    library.seccomp_rule_add_array.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_notify_fd.argtypes = [ctypes.c_void_p]
    library.seccomp_notify_fd.restype = ctypes.c_int
    context = library.seccomp_init(SCMP_ACT_ALLOW)
    if not context:
        error = ctypes.get_errno()
        raise OSError(error or errno.ENOMEM, os.strerror(error or errno.ENOMEM))
    try:
        unix_comparison = SeccompArgCompare(
            arg=0,
            op=SCMP_CMP_EQ,
            datum_a=socket.AF_UNIX,
            datum_b=0,
        )
        for syscall_name in (b"socketpair",):
            syscall = int(library.seccomp_syscall_resolve_name(syscall_name))
            if syscall < 0:
                raise RuntimeError(
                    f"libseccomp cannot resolve {syscall_name.decode('ascii')}"
                )
            result = int(
                library.seccomp_rule_add_array(
                    context,
                    SCMP_ACT_ERRNO | errno.EPERM,
                    syscall,
                    1,
                    ctypes.byref(unix_comparison),
                )
            )
            if result != 0:
                raise OSError(-result, os.strerror(-result))
        socket_syscall = int(library.seccomp_syscall_resolve_name(b"socket"))
        if socket_syscall < 0:
            raise RuntimeError("libseccomp cannot resolve socket")
        for family in range(64):
            if family in (socket.AF_INET, socket.AF_INET6):
                continue
            comparison = SeccompArgCompare(
                arg=0,
                op=SCMP_CMP_EQ,
                datum_a=family,
                datum_b=0,
            )
            result = int(
                library.seccomp_rule_add_array(
                    context,
                    SCMP_ACT_ERRNO | errno.EPERM,
                    socket_syscall,
                    1,
                    ctypes.byref(comparison),
                )
            )
            if result != 0:
                raise OSError(-result, os.strerror(-result))
        for family in (socket.AF_INET, socket.AF_INET6):
            for socket_type in range(16):
                if socket_type == socket.SOCK_STREAM:
                    continue
                comparisons = (SeccompArgCompare * 2)(
                    SeccompArgCompare(
                        arg=0,
                        op=SCMP_CMP_EQ,
                        datum_a=family,
                        datum_b=0,
                    ),
                    SeccompArgCompare(
                        arg=1,
                        op=SCMP_CMP_MASKED_EQ,
                        datum_a=SOCK_TYPE_MASK,
                        datum_b=socket_type,
                    ),
                )
                result = int(
                    library.seccomp_rule_add_array(
                        context,
                        SCMP_ACT_ERRNO | errno.EPERM,
                        socket_syscall,
                        2,
                        comparisons,
                    )
                )
                if result != 0:
                    raise OSError(-result, os.strerror(-result))
        for syscall_name in (b"connect", b"bind", b"listen"):
            syscall = int(library.seccomp_syscall_resolve_name(syscall_name))
            if syscall < 0:
                raise RuntimeError(
                    f"libseccomp cannot resolve {syscall_name.decode('ascii')}"
                )
            result = int(
                library.seccomp_rule_add_array(
                    context,
                    SCMP_ACT_NOTIFY,
                    syscall,
                    0,
                    None,
                )
            )
            if result != 0:
                raise OSError(-result, os.strerror(-result))
        for syscall_name, flags_argument in (
            (b"sendto", 3),
            (b"sendmsg", 2),
            (b"sendmmsg", 3),
        ):
            syscall = int(library.seccomp_syscall_resolve_name(syscall_name))
            if syscall < 0:
                raise RuntimeError(
                    f"libseccomp cannot resolve {syscall_name.decode('ascii')}"
                )
            comparison = SeccompArgCompare(
                arg=flags_argument,
                op=SCMP_CMP_MASKED_EQ,
                datum_a=MSG_FASTOPEN,
                datum_b=MSG_FASTOPEN,
            )
            result = int(
                library.seccomp_rule_add_array(
                    context,
                    SCMP_ACT_ERRNO | errno.EPERM,
                    syscall,
                    1,
                    ctypes.byref(comparison),
                )
            )
            if result != 0:
                raise OSError(-result, os.strerror(-result))
        for syscall_name in (
            b"io_uring_setup",
            b"io_uring_enter",
            b"io_uring_register",
        ):
            syscall = int(library.seccomp_syscall_resolve_name(syscall_name))
            if syscall < 0:
                raise RuntimeError(
                    f"libseccomp cannot resolve {syscall_name.decode('ascii')}"
                )
            result = int(
                library.seccomp_rule_add_array(
                    context,
                    SCMP_ACT_ERRNO | errno.EPERM,
                    syscall,
                    0,
                    None,
                )
            )
            if result != 0:
                raise OSError(-result, os.strerror(-result))
        result = int(library.seccomp_load(context))
        if result != 0:
            raise OSError(-result, os.strerror(-result))
        listener = int(library.seccomp_notify_fd(context))
        if listener < 0:
            raise OSError(-listener, os.strerror(-listener))
    finally:
        library.seccomp_release(context)
    return (
        listener,
        "libseccomp-explicit-loopback-port-connect-bind-listen-broker-"
        "tcp-fast-open-deny-"
        "no-af-unix-datagram-raw-or-io-uring",
    )


def _send_descriptor(channel: socket.socket, descriptor: int) -> None:
    payload = array.array("i", [descriptor])
    channel.sendmsg(
        [b"N"],
        [(socket.SOL_SOCKET, socket.SCM_RIGHTS, payload.tobytes())],
    )


def _receive_descriptor(channel: socket.socket) -> int:
    message, ancillary, _flags, _address = channel.recvmsg(
        1,
        socket.CMSG_SPACE(array.array("i").itemsize),
    )
    if message != b"N":
        raise RuntimeError("network broker child did not provide its listener")
    for level, kind, payload in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            descriptors = array.array("i")
            descriptors.frombytes(payload[: descriptors.itemsize])
            if len(descriptors) == 1:
                return int(descriptors[0])
    raise RuntimeError("network broker listener descriptor is missing")


def _read_process_memory(pid: int, address: int, length: int) -> bytes:
    if address <= 0 or length <= 0 or length > 128:
        raise OSError(errno.EFAULT, os.strerror(errno.EFAULT))
    libc = ctypes.CDLL(None, use_errno=True)
    buffer = (ctypes.c_ubyte * length)()
    local = IOVec(ctypes.cast(buffer, ctypes.c_void_p), length)
    remote = IOVec(ctypes.c_void_p(address), length)
    libc.process_vm_readv.argtypes = [
        ctypes.c_int,
        ctypes.POINTER(IOVec),
        ctypes.c_ulong,
        ctypes.POINTER(IOVec),
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    libc.process_vm_readv.restype = ctypes.c_ssize_t
    result = int(
        libc.process_vm_readv(
            pid,
            ctypes.byref(local),
            1,
            ctypes.byref(remote),
            1,
            0,
        )
    )
    if result != length:
        error = ctypes.get_errno() if result < 0 else errno.EFAULT
        raise OSError(error, os.strerror(error))
    return bytes(buffer)


def _thread_group_id(thread_id: int) -> int:
    with open(f"/proc/{thread_id}/status", encoding="ascii") as handle:
        for line in handle:
            if line.startswith("Tgid:"):
                return int(line.split(":", 1)[1].strip())
    raise OSError(errno.ESRCH, os.strerror(errno.ESRCH))


def _duplicate_tracee_descriptor(thread_id: int, descriptor: int) -> int:
    process_id = _thread_group_id(thread_id)
    pidfd = os.pidfd_open(process_id, 0)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        duplicate = int(libc.syscall(SYS_PIDFD_GETFD, pidfd, descriptor, 0))
        if duplicate < 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        return duplicate
    finally:
        os.close(pidfd)


def _loopback_sockaddr(payload: bytes, allowed_ports: frozenset[int]) -> bool:
    if len(payload) < 2:
        return False
    family = struct.unpack_from("=H", payload)[0]
    port = struct.unpack_from("!H", payload, 2)[0] if len(payload) >= 4 else 0
    if port not in allowed_ports:
        return False
    if family == socket.AF_INET:
        return len(payload) >= 16 and ipaddress.ip_address(payload[4:8]).is_loopback
    if family == socket.AF_INET6:
        return len(payload) >= 28 and ipaddress.ip_address(payload[8:24]).is_loopback
    return False


def _broker_address_call(
    notification: SeccompNotification,
    allowed_ports: frozenset[int],
    operation: str,
) -> int:
    address_length = int(notification.data.args[2])
    try:
        sockaddr = _read_process_memory(
            int(notification.pid),
            int(notification.data.args[1]),
            address_length,
        )
        if not _loopback_sockaddr(sockaddr, allowed_ports):
            return errno.EPERM
        duplicate = _duplicate_tracee_descriptor(
            int(notification.pid),
            int(notification.data.args[0]),
        )
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            buffer = ctypes.create_string_buffer(sockaddr)
            function = getattr(libc, operation)
            result = int(
                function(
                    duplicate, ctypes.cast(buffer, ctypes.c_void_p), address_length
                )
            )
            return 0 if result == 0 else ctypes.get_errno()
        finally:
            os.close(duplicate)
    except (OSError, ValueError):
        return errno.EPERM


def _broker_listen(
    notification: SeccompNotification,
    allowed_ports: frozenset[int],
) -> int:
    try:
        duplicate = _duplicate_tracee_descriptor(
            int(notification.pid),
            int(notification.data.args[0]),
        )
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            sockaddr = ctypes.create_string_buffer(128)
            address_length = ctypes.c_uint32(len(sockaddr))
            result = int(
                libc.getsockname(
                    duplicate,
                    ctypes.cast(sockaddr, ctypes.c_void_p),
                    ctypes.byref(address_length),
                )
            )
            if result != 0:
                return ctypes.get_errno()
            if not _loopback_sockaddr(
                bytes(sockaddr.raw[: address_length.value]),
                allowed_ports,
            ):
                return errno.EPERM
            result = int(libc.listen(duplicate, int(notification.data.args[1])))
            return 0 if result == 0 else ctypes.get_errno()
        finally:
            os.close(duplicate)
    except (OSError, ValueError):
        return errno.EPERM


def _broker_network_call(
    notification: SeccompNotification,
    *,
    connect_syscall: int,
    bind_syscall: int,
    listen_syscall: int,
    allowed_connect_ports: frozenset[int],
    allowed_bind_ports: frozenset[int],
) -> int:
    syscall = int(notification.data.nr)
    if syscall == connect_syscall:
        return _broker_address_call(
            notification,
            allowed_connect_ports,
            "connect",
        )
    if syscall == bind_syscall:
        return _broker_address_call(notification, allowed_bind_ports, "bind")
    if syscall == listen_syscall:
        return _broker_listen(notification, allowed_bind_ports)
    return errno.EPERM


def _serve_network_notifications(
    listener: int,
    child_pid: int,
    seccomp_path: str,
    allowed_connect_ports: frozenset[int],
    allowed_bind_ports: frozenset[int],
) -> int:
    # Notification helpers are resolved only from the already validated,
    # operator-pinned libseccomp path.
    seccomp = ctypes.CDLL(seccomp_path, use_errno=True)
    seccomp.seccomp_notify_alloc.argtypes = [
        ctypes.POINTER(ctypes.POINTER(SeccompNotification)),
        ctypes.POINTER(ctypes.POINTER(SeccompNotificationResponse)),
    ]
    seccomp.seccomp_notify_alloc.restype = ctypes.c_int
    seccomp.seccomp_notify_free.argtypes = [
        ctypes.POINTER(SeccompNotification),
        ctypes.POINTER(SeccompNotificationResponse),
    ]
    seccomp.seccomp_notify_free.restype = None
    seccomp.seccomp_notify_receive.argtypes = [
        ctypes.c_int,
        ctypes.POINTER(SeccompNotification),
    ]
    seccomp.seccomp_notify_receive.restype = ctypes.c_int
    seccomp.seccomp_notify_respond.argtypes = [
        ctypes.c_int,
        ctypes.POINTER(SeccompNotificationResponse),
    ]
    seccomp.seccomp_notify_respond.restype = ctypes.c_int
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_syscall_resolve_name.restype = ctypes.c_int
    connect_syscall = int(seccomp.seccomp_syscall_resolve_name(b"connect"))
    bind_syscall = int(seccomp.seccomp_syscall_resolve_name(b"bind"))
    listen_syscall = int(seccomp.seccomp_syscall_resolve_name(b"listen"))
    if min(connect_syscall, bind_syscall, listen_syscall) < 0:
        raise RuntimeError("network broker cannot resolve required socket syscalls")

    pidfd = os.pidfd_open(child_pid, 0)
    poller = select.poll()
    poller.register(listener, select.POLLIN)
    poller.register(pidfd, select.POLLIN)
    try:
        while True:
            for descriptor, events in poller.poll(1000):
                if descriptor == pidfd and events:
                    _pid, status = os.waitpid(child_pid, 0)
                    if os.WIFEXITED(status):
                        return os.WEXITSTATUS(status)
                    if os.WIFSIGNALED(status):
                        return 128 + os.WTERMSIG(status)
                    return 125
                if descriptor != listener or not events & select.POLLIN:
                    continue
                notification = ctypes.POINTER(SeccompNotification)()
                response = ctypes.POINTER(SeccompNotificationResponse)()
                allocated = int(
                    seccomp.seccomp_notify_alloc(
                        ctypes.byref(notification),
                        ctypes.byref(response),
                    )
                )
                if allocated != 0:
                    raise OSError(-allocated, os.strerror(-allocated))
                try:
                    received = int(
                        seccomp.seccomp_notify_receive(listener, notification)
                    )
                    if received in (-errno.ENOENT, -errno.EINTR):
                        continue
                    if received != 0:
                        raise OSError(-received, os.strerror(-received))
                    error = _broker_network_call(
                        notification.contents,
                        connect_syscall=connect_syscall,
                        bind_syscall=bind_syscall,
                        listen_syscall=listen_syscall,
                        allowed_connect_ports=allowed_connect_ports,
                        allowed_bind_ports=allowed_bind_ports,
                    )
                    response.contents.id = notification.contents.id
                    response.contents.val = 0
                    response.contents.error = -error if error else 0
                    response.contents.flags = 0
                    responded = int(
                        seccomp.seccomp_notify_respond(listener, response)
                    )
                    if responded not in (0, -errno.ENOENT):
                        raise OSError(-responded, os.strerror(-responded))
                finally:
                    seccomp.seccomp_notify_free(notification, response)
    finally:
        os.close(pidfd)
        os.close(listener)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seccomp-library", required=True)
    parser.add_argument("--allow-write", action="append", required=True)
    parser.add_argument("--allow-connect-port", action="append", type=int, default=[])
    parser.add_argument("--allow-bind-port", action="append", type=int, default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    result = parser.parse_args(argv)
    if result.command and result.command[0] == "--":
        result.command = result.command[1:]
    if not result.command:
        parser.error("a command after -- is required")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    allowed = tuple(_resolve_directory(path) for path in args.allow_write)
    allowed_ports = frozenset(args.allow_connect_port)
    allowed_bind_ports = frozenset(args.allow_bind_port)
    if (
        len(allowed_ports) != len(args.allow_connect_port)
        or any(port < 1 or port > 65535 for port in allowed_ports)
        or len(allowed_bind_ports) != len(args.allow_bind_port)
        or any(port < 1 or port > 65535 for port in allowed_bind_ports)
    ):
        raise ValueError("network allowances must be unique TCP ports from 1 through 65535")
    seccomp_library = _resolve_seccomp_library(args.seccomp_library)
    command = Path(args.command[0])
    if not command.is_absolute():
        raise ValueError("isolated command executable must be absolute")
    executable = command.resolve(strict=True)
    metadata = executable.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o111 == 0:
        raise ValueError(f"isolated command executable is not executable: {executable}")
    parent_channel, child_channel = socket.socketpair(
        socket.AF_UNIX,
        socket.SOCK_DGRAM | socket.SOCK_CLOEXEC,
    )
    parent_pid = os.getpid()
    child_pid = os.fork()
    if child_pid == 0:
        parent_channel.close()
        try:
            os.setpgid(0, 0)
            libc = ctypes.CDLL(None, use_errno=True)
            if int(libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
            if os.getppid() != parent_pid:
                raise RuntimeError("network broker parent exited before isolation")
            abi = enforce_write_isolation(allowed)
            listener, seccomp = install_network_seccomp(str(seccomp_library))
            try:
                _send_descriptor(child_channel, listener)
            finally:
                os.close(listener)
                child_channel.close()
            environment = dict(os.environ)
            environment["CHUMMER_LANDLOCK_WRITE_ISOLATION"] = f"abi-{abi}"
            environment["CHUMMER_SECCOMP_SOCKET_ISOLATION"] = seccomp
            os.execve(executable, [str(executable), *args.command[1:]], environment)
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"landlock_exec: {exc}", file=sys.stderr, flush=True)
            os._exit(125)

    child_channel.close()

    def forward_signal(signum: int, _frame: object) -> None:
        try:
            os.killpg(child_pid, signum)
        except ProcessLookupError:
            pass

    for handled_signal in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(handled_signal, forward_signal)
    try:
        listener = _receive_descriptor(parent_channel)
    except Exception:
        try:
            os.killpg(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(child_pid, 0)
        raise
    finally:
        parent_channel.close()
    try:
        return _serve_network_notifications(
            listener,
            child_pid,
            str(seccomp_library),
            allowed_ports,
            allowed_bind_ports,
        )
    except Exception:
        try:
            os.killpg(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(child_pid, 0)
        except ChildProcessError:
            pass
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"landlock_exec: {exc}", file=sys.stderr)
        raise SystemExit(125)
