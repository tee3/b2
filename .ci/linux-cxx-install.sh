#!/bin/sh

# Usage:
# LLVM_OS: LLVM OS release to obtain clang binaries. Only needed for clang install.
# LLVM_VER: The LLVM toolset version to point the repo at.
# PACKAGES: Compiler packages to install.

set -e
set -u

if command -v sudo ; then
    SUDO="sudo -E"
fi
OS_ISSUE="$(cat /etc/issue | head -n1 | cut -d " " -f1)"
printf ">>>>> OS Issue: %s\n" "${OS_ISSUE}"

PACKAGES="${PACKAGES:-build-essential}"

set -e
printf ">>>>>\n"
printf ">>>>> APT: UPDATE..\n"
printf ">>>>>\n"
${SUDO} apt-get -o Acquire::Retries=3 update
printf ">>>>>\n"
printf ">>>>> APT: REPO..\n"
printf ">>>>>\n"
${SUDO} apt-get -o Acquire::Retries=3 -y install software-properties-common
if test "${OS_ISSUE}" = "Ubuntu" ; then
    ${SUDO} apt-add-repository -y "ppa:ubuntu-toolchain-r/test"
fi
if test -n "${LLVM_OS}" ; then
	wget -O - https://apt.llvm.org/llvm-snapshot.gpg.key | sudo apt-key add -
	${SUDO} apt-add-repository "deb http://apt.llvm.org/${LLVM_OS}/ llvm-toolchain-${LLVM_OS}-${LLVM_VER} main"
fi
printf ">>>>>\n"
printf ">>>>> APT: UPDATE..\n"
printf ">>>>>\n"
${SUDO} apt-get -o Acquire::Retries=3 update
printf ">>>>>\n"
printf ">>>>> APT: INSTALL %s..\n" "${PACKAGES}"
printf ">>>>>\n"
${SUDO} apt-get -o Acquire::Retries=3 -yq --no-install-suggests --no-install-recommends install ${PACKAGES}

# Use, modification, and distribution are
# subject to the Boost Software License, Version 1.0. (See accompanying
# file LICENSE.txt)
#
# Copyright Rene Rivera 2020.
