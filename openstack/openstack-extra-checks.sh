#!/bin/bash -u
# Copyright 2020 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Authors:
#  - edward.hope-morley@canonical.com

export OPENRC=${1:-""}

# Install dependencies
dpkg -s jq &>/dev/null || sudo apt install -y jq

# Run Tests
cat << EOF
================================================================================
Running extra Openstack checks on `date`.
================================================================================

EOF

if [ -z "$OPENRC" ] || ! [ -r "$OPENRC" ]; then
    read -p "Path to openstack credentials file (openrc): " OPENRC
fi
. $OPENRC

# See function definitions for explanation.
CHECKS_DIR=`dirname $0`/extra-checks.d

echo -e "\nRunning Glance image format test"
$CHECKS_DIR/glance && echo "Result: [PASS]" || echo "Result: [FAIL]"

echo -e "\nRunning Octavia LoadBalancer test"
$CHECKS_DIR/octavia && echo "Result: [PASS]" || echo "Result: [FAIL]"

echo -e "\nDone."
