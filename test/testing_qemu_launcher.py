#!/usr/bin/env python3
#
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE.txt or copy at
# https://www.bfgroup.xyz/b2/LICENSE.txt)

# Test that tests of a foreign <architecture> Linux target are run under the
# matching QEMU user mode emulator, when one is available, and that an explicit
# <testing.launcher> still takes precedence.

import BoostBuild
import os
import platform
import stat
import sys
import textwrap

MOCK_COMPILER = '''#!/usr/bin/env python3
import os
import stat
import sys

args = sys.argv[1:]

if args == ["-dumpmachine"]:
    print("x86_64-linux-gnu")
    sys.exit(0)

if args == ["-print-prog-name=ar"]:
    print("ar")
    sys.exit(0)

if "-o" in args:
    output = args[args.index("-o") + 1]
    with open(output, "w") as f:
        f.write("#!/bin/sh\\nexit 0\\n")
    os.chmod(output, os.stat(output).st_mode | stat.S_IXUSR)
    sys.exit(0)

sys.exit(1)
'''

MOCK_QEMU = '''#!/bin/sh
echo "$0" "$@" >> "@MARKER@"
exec "$1"
'''

NATIVE = {
    "x86_64": ["architecture=x86", "address-model=64"],
    "amd64": ["architecture=x86", "address-model=64"],
    "aarch64": ["architecture=arm", "address-model=64"],
    "arm64": ["architecture=arm", "address-model=64"],
}.get(platform.machine().lower())


def make_tester():
    t = BoostBuild.Tester(pass_toolset=0)
    t.write("fake-compiler.py", MOCK_COMPILER)
    t.write("project-config.jam", textwrap.dedent('''
        import os ;
        path-constant HERE : . ;
        local PYTHON = [ os.environ PYTHON_CMD ] ;
        using gcc : mock : $(PYTHON) $(HERE)/fake-compiler.py ;
        '''))
    t.write("Jamroot.jam", textwrap.dedent('''
        import testing ;
        unit-test ut : test.cpp ;
        run test.cpp : : : : rt ;
        unit-test explicit : test.cpp : <testing.launcher>"@LAUNCHER@" ;
        '''.replace("@LAUNCHER@", t.native_file_name("fake-bin/explicit"))))
    t.write("test.cpp", "int main() { return 0; }")
    for name in ["qemu-riscv64", "explicit"]:
        t.write("fake-bin/" + name,
            MOCK_QEMU.replace("@MARKER@", t.native_file_name(name + ".log")))
        path = t.native_file_name("fake-bin/" + name)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return t


def run(t, *args):
    path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.path.join(t.workdir, "fake-bin") + os.pathsep + path
    try:
        t.run_build_system(["-sPYTHON_CMD=" + sys.executable,
            "toolset=gcc-mock", "target-os=linux"] + list(args))
    finally:
        os.environ["PATH"] = path


def launched(t, name):
    log = os.path.join(t.workdir, name + ".log")
    if not os.path.exists(log):
        return []
    with open(log) as f:
        return f.read().splitlines()


def test_foreign_target_uses_qemu():
    t = make_tester()
    run(t, "architecture=riscv", "address-model=64", "ut", "rt")
    runs = launched(t, "qemu-riscv64")
    if len(runs) != 2 or not all("qemu-riscv64" in r for r in runs):
        t.fail_test(1)
    t.cleanup()


def test_explicit_launcher_wins():
    t = make_tester()
    run(t, "architecture=riscv", "address-model=64", "explicit")
    if launched(t, "qemu-riscv64") or len(launched(t, "explicit")) != 1:
        t.fail_test(1)
    t.cleanup()


def test_no_qemu_without_architecture():
    t = make_tester()
    run(t, "ut")
    if launched(t, "qemu-riscv64"):
        t.fail_test(1)
    t.cleanup()


def test_no_qemu_for_native_target():
    t = make_tester()
    os.rename(os.path.join(t.workdir, "fake-bin", "qemu-riscv64"),
        os.path.join(t.workdir, "fake-bin", "qemu-" + platform.machine()))
    run(t, "ut", *NATIVE)
    if launched(t, "qemu-riscv64"):
        t.fail_test(1)
    t.cleanup()


# QEMU user mode emulation only runs Linux executables on a Linux host.
if sys.platform.startswith("linux"):
    test_foreign_target_uses_qemu()
    test_explicit_launcher_wins()
    test_no_qemu_without_architecture()
    if NATIVE:
        test_no_qemu_for_native_target()
