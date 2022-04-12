#!/bin/sh

set -e

cdir="${PWD}"
cd "$1"
"${HOME}"/temp/.b2/bin/b2 -d+2 "${B2_ARGS}"
printf "%s\n" "-----"
find . -perm -111 -type f -exec file "{}" "+"
printf "%s\n" "-----"
find . -name "*.o" -exec file "{}" "+"
printf "%s\n" "-----"
find . -name "*.a" -exec file "{}" "+"
printf "%s\n" "-----"
find . -name "*.so" -exec file "{}" "+"
printf "%s\n" "-----"
find . -name "*.dylib" -exec file "{}" "+"
printf "%s\n" "-----"
cd "${cdir}"

# Use, modification, and distribution are
# subject to the Boost Software License, Version 1.0. (See accompanying
# file LICENSE.txt)
#
# Copyright Rene Rivera 2022.
