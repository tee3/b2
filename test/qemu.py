#!/usr/bin/env python3
#
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE.txt or copy at
# https://www.bfgroup.xyz/b2/LICENSE.txt)

# Test that `using qemu` runs the tests of Linux targets for other processors
# under the matching QEMU user mode emulator and CPU, fails the tests it has no
# emulator for, and leaves the rest alone.

import BoostBuild
import os
import platform
import re
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

# Answers --version and -cpu help, also when last as through a command
# such as a container, and otherwise logs its arguments separated by |.
MOCK_QEMU = '''#!/bin/sh
for last; do :; done
if [ "$last" = "--version" ]; then
    echo "qemu version 10.0.13 (mock)"
    exit 0
fi
if [ "$last" = "help" ]; then
    echo "Available CPUs:"
    echo "  cortex-a7"
    echo "  cortex-r5f"
    exit 0
fi
{ printf %s "$(basename "$0")"; for x; do printf "|%s" "$x"; done; echo; } \\
    >> "@LOG@"
'''

EMULATORS = ["qemu-riscv64", "qemu-arm", "qemu-s390x", "qemu-mipsel",
    "qemu-mips", "explicit", "container", "qemu-system-arm"]

# The host runs 32 bit arm natively, so it is not emulated.
ARM_HOST = platform.machine().lower().startswith("arm")

NATIVE = {
    "x86_64": ["architecture=x86", "address-model=64"],
    "amd64": ["architecture=x86", "address-model=64"],
    "aarch64": ["architecture=arm", "address-model=64"],
    "arm64": ["architecture=arm", "address-model=64"],
}.get(platform.machine().lower())


def make_tester(options="", command="$(HERE)/fake-bin/qemu-arm", version=""):
    t = BoostBuild.Tester(pass_toolset=0)
    t.write("fake-compiler.py", MOCK_COMPILER)
    t.write("project-config.jam", textwrap.dedent('''
        import os ;
        path-constant HERE : . ;
        local PYTHON = [ os.environ PYTHON_CMD ] ;
        using gcc : mock : $(PYTHON) $(HERE)/fake-compiler.py ;
        using qemu : @VERSION@ : @COMMAND@ : @OPTIONS@ ;
        ''').replace("@OPTIONS@", options).replace("@COMMAND@", command)
        .replace("@VERSION@", version))
    t.write("Jamroot.jam", textwrap.dedent('''
        import testing ;
        unit-test ut : test.cpp ;
        run test.cpp : : : : rt ;
        run test.cpp : one two : : : withargs ;
        run test.cpp : "one two" "a,b" : : : spaced ;
        unit-test explicit : test.cpp : <testing.launcher>"@LAUNCHER@" ;
        '''.replace("@LAUNCHER@", t.native_file_name("fake-bin/explicit"))))
    t.write("test.cpp", "int main() { return 0; }")
    for name in EMULATORS:
        t.write("fake-bin/" + name,
            MOCK_QEMU.replace("@LOG@", t.native_file_name("qemu.log")))
        path = t.native_file_name("fake-bin/" + name)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return t


def run(t, *args, **kwargs):
    target_os = [] if [a for a in args if a.startswith("target-os=")] \
        else ["target-os=linux"]
    # The runs are checked in the log and output, not in any tool noise.
    kwargs.setdefault("stderr", None)
    t.run_build_system(["-sPYTHON_CMD=" + sys.executable, "toolset=gcc-mock",
        "-a"] + target_os + list(args), **kwargs)


def launched(t, raw=False):
    log = t.native_file_name("qemu.log")
    if not os.path.exists(log):
        return []
    with open(log) as f:
        runs = f.read().splitlines()
    os.remove(log)
    return runs if raw else [r.replace("|", " ") for r in runs]


def expect_runs(t, *expected):
    # Without the test executable, which is last.
    runs = [r.rsplit(" ", 1)[0] for r in launched(t)]
    if sorted(runs) != sorted(expected):
        print("expected runs:", sorted(expected))
        print("actual runs:  ", sorted(runs))
        t.fail_test(1)


def expect_error(t, message, *args):
    run(t, *args, status=1)
    t.expect_output_lines("*error: qemu: " + message + "*")
    expect_runs(t)


def test_emulator_cpu_and_options():
    t = make_tester("<qemu-sysroot>riscv.64=/opt/riscv <qemu-option>-B "
        "<qemu-option>0x100000 <qemu-cpu>cortex-a53=cortex-a7 "
        "<qemu-cpu>cortex-r5=")

    # The emulator from architecture and address-model, with the options.
    run(t, "architecture=riscv", "address-model=64", "ut", "rt")
    expect_runs(t, *["qemu-riscv64 -L /opt/riscv -B 0x100000"] * 2)

    # A CPU of the same name.
    run(t, "architecture=s390x", "address-model=64", "instruction-set=z13",
        "ut")
    expect_runs(t, "qemu-s390x -B 0x100000 -cpu z13")

    if not ARM_HOST:
        # A CPU from the table, whose name differs.
        run(t, "architecture=arm", "address-model=32",
            "instruction-set=cortex-r5+vfpv3-d16", "ut")
        expect_runs(t, "qemu-arm -B 0x100000 -cpu cortex-r5f")

        # A CPU given with <qemu-cpu>.
        run(t, "architecture=arm", "address-model=32",
            "instruction-set=cortex-a53", "ut")
        expect_runs(t, "qemu-arm -B 0x100000 -cpu cortex-a7")

        # Not in the table, so passed as it is.
        run(t, "architecture=arm", "address-model=32",
            "instruction-set=armv7", "ut")
        expect_runs(t, "qemu-arm -B 0x100000 -cpu armv7")

        # None, given with an empty <qemu-cpu>.
        run(t, "architecture=arm", "address-model=32",
            "instruction-set=cortex-r5", "ut")
        expect_runs(t, "qemu-arm -B 0x100000")

    # An explicit launcher is used instead.
    run(t, "architecture=riscv", "address-model=64", "explicit")
    expect_runs(t, "explicit")

    t.cleanup()


def test_errors():
    t = make_tester()

    expect_error(t, "no QEMU emulator is known for architecture=ia64 "
        "address-model=64*", "architecture=ia64", "address-model=64", "rt")
    expect_error(t, "architecture=riscv needs an address-model*",
        "architecture=riscv", "ut")

    t.cleanup()


def test_byte_order():
    t = make_tester()

    # Little endian, as B2 does not know the byte order.
    run(t, "architecture=mips", "address-model=32", "instruction-set=24kc",
        "ut")
    expect_runs(t, "qemu-mipsel -cpu 24Kc")

    t.cleanup()

    # Big endian when given.
    t = make_tester("<qemu-emulator>mips.32=qemu-mips")

    run(t, "architecture=mips", "address-model=32", "instruction-set=24kc",
        "ut")
    expect_runs(t, "qemu-mips -cpu 24Kc")

    t.cleanup()


def test_native_and_host_targets():
    t = make_tester()

    run(t, "ut")
    expect_runs(t)
    if NATIVE:
        run(t, "ut", *NATIVE)
        expect_runs(t)

    t.cleanup()


def test_command():
    # A command that runs QEMU, in a container, which passes on the library
    # path that the test sets up.
    library_path = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" \
        else "LD_LIBRARY_PATH"
    t = make_tester(command="$(HERE)/fake-bin/container exec -w $PWD "
        "-e LD_LIBRARY_PATH=$" + library_path + " b2-test qemu-arm")

    def expect_command_runs(*expected):
        runs = []
        for r in launched(t):
            r = r.rsplit(" ", 1)[0].split(" ")
            # The directory, and the library path, here of the mock gcc.
            if r[3] != os.path.realpath(t.workdir) or "/lib64" not in r[5]:
                print("directory or library path not passed on:", r)
                t.fail_test(1)
            runs.append(" ".join(r[:3] + ["DIR"] + r[4:5] + ["PATH"] + r[6:]))
        if sorted(runs) != sorted(expected):
            print("expected runs:", sorted(expected))
            print("actual runs:  ", sorted(runs))
            t.fail_test(1)

    # Other processors under QEMU with the command, which is given the
    # program, and the system root, as they are.
    run(t, "architecture=riscv", "address-model=64", "ut", "rt")
    expect_command_runs(*["container exec -w DIR -e PATH b2-test qemu-riscv64 "
        "-L /usr/riscv64-linux-gnu"] * 2)

    # The host's own processor, or none given, directly with the command.
    run(t, "ut")
    expect_command_runs("container exec -w DIR -e PATH b2-test")
    if NATIVE:
        run(t, "ut", *NATIVE)
        expect_command_runs("container exec -w DIR -e PATH b2-test")

    t.cleanup()


def test_bare_metal():
    t = make_tester("<qemu-machine>versatilepb "
        "<qemu-machine>cortex-a9+vfpv3=realview-pbx-a9")

    def expect_bare_metal_runs(*expected):
        runs = [re.sub(r"bin/\S*/(\w+)\b", r"\1", r) for r in launched(t)]
        if sorted(runs) != sorted(expected):
            print("expected runs:", sorted(expected))
            print("actual runs:  ", sorted(runs))
            t.fail_test(1)

    semihosting = " -semihosting-config enable=on,target=native,arg="

    # The machine for all targets, and the test as the kernel.
    run(t, "target-os=elf", "architecture=arm", "address-model=32", "ut",
        "withargs")
    expect_bare_metal_runs(
        "qemu-system-arm -M versatilepb -display none -audio none "
        "-kernel ut" + semihosting + "ut",
        "qemu-system-arm -M versatilepb -display none -audio none "
        "-kernel withargs" + semihosting + "withargs,arg=one,arg=two")

    # Arguments with commas, which QEMU needs doubled. B2 passes the
    # arguments of tests to the shell as they are, so "one two" is two.
    run(t, "target-os=elf", "architecture=arm", "address-model=32", "spaced")
    runs = launched(t, raw=True)
    if len(runs) != 1 or "|enable=on,target=native,arg=" not in runs[0] or \
            not runs[0].endswith("spaced,arg=one,arg=two,arg=a,,b"):
        print("actual runs:", runs)
        t.fail_test(1)

    # The machine for an instruction-set, with its CPU.
    run(t, "target-os=elf", "architecture=arm", "address-model=32",
        "instruction-set=cortex-a9+vfpv3", "ut")
    expect_bare_metal_runs("qemu-system-arm -M realview-pbx-a9 -cpu cortex-a9 "
        "-display none -audio none -kernel ut" + semihosting + "ut")

    # No emulator for the architecture.
    expect_error(t, "bare metal tests need an architecture*",
        "target-os=elf", "ut")

    t.cleanup()

    # No machine.
    t = make_tester()
    expect_error(t, "bare metal tests need a machine*", "target-os=none",
        "architecture=arm", "address-model=32", "ut")
    t.cleanup()


def test_version():
    # A version that matches the QEMU found.
    t = make_tester(version="10.0")
    run(t, "-n", "ut")
    t.cleanup()

    # One that does not.
    t = make_tester(version="9.2")
    run(t, "-n", "ut", status=1)
    t.expect_output_lines("*qemu: version 9.2 was given, but QEMU version "
        "10.0.13 was found*")
    t.cleanup()

    # One given, and no QEMU found.
    t = make_tester(command="$(HERE)/no-bin/qemu-arm", version="10.0")
    run(t, "-n", "ut")
    t.cleanup()

    # None given, and no QEMU found.
    t = make_tester(command="$(HERE)/no-bin/qemu-arm")
    run(t, "-n", "ut", status=1)
    t.expect_output_lines("*qemu: no QEMU was found to get its version from*")
    t.cleanup()


def test_options():
    for options, message in [
            ("<qemu-foo>bar", "unknown option <qemu-foo>bar"),
            ("<qemu-cpu>cortex-a53", "invalid option <qemu-cpu>cortex-a53"),
            ("<qemu-emulator>arm.32", "invalid option <qemu-emulator>arm.32"),
            ("<qemu-check>yes", "invalid option <qemu-check>yes")]:
        t = make_tester(options)
        run(t, "-n", "ut", status=1)
        t.expect_output_lines("*qemu: " + message + " in using qemu*")
        t.cleanup()

    # Configuring again differently is warned about.
    t = make_tester()
    t.write("project-config.jam", t.read("project-config.jam") +
        "using qemu : 10.0 ;\n")
    run(t, "-n", "ut")
    t.expect_output_lines("warning: qemu: already configured*")
    t.cleanup()


def test_check():
    t = make_tester("<qemu-check>on")
    run(t, "-n", "ut")
    t.expect_output_lines("warning: qemu: qemu-arm does not list the CPU "
        "cortex-a9.")
    if "does not list the CPU cortex-r5f" in t.stdout() or \
            t.stdout().count("does not list the CPU cortex-a9.") != 1:
        t.fail_test(1)
    t.cleanup()


def test_other_hosts():
    t = make_tester()

    # Only configured, as the mock test executable can not run everywhere.
    run(t, "architecture=riscv", "address-model=64", "-n", "ut")
    t.expect_output_lines("warning: qemu: user mode emulation is only "
        "available on Linux hosts*")
    expect_runs(t)

    t.cleanup()


if sys.platform.startswith("linux"):
    test_emulator_cpu_and_options()
    test_errors()
    test_byte_order()
    test_native_and_host_targets()
else:
    test_other_hosts()
if not sys.platform.startswith("win"):
    test_version()
    test_options()
    test_command()
    test_bare_metal()
if sys.platform.startswith("linux") and not ARM_HOST:
    test_check()
