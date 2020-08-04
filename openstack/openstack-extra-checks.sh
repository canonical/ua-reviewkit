#!/bin/bash
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

MAX_WAIT_ACTIVE=50
OPENRC=${1:-""}

_delete_lb ()
{
    openstack loadbalancer delete --cascade $1
}

test_octavia_lb ()
{
    ## OCTAVIA LOADBALANCER TEST
    #
    # This test requires project net, subnet, ext net and vm. These can be
    # provided using env vars otherwise input is requested.
    #
    # export UA_OS_CHECKS_PROJECT_NET=<tenant network name or uuid>
    # export UA_OS_CHECKS_PROJECT_SUBNET=<tenant subnet name or uuid>
    # export UA_OS_CHECKS_EXT_NET=<external net name or uuid>
    # export UA_OS_CHECKS_VM_UUID=<vm uuid>

    local rc=0
    local net=$1
    local subnet=$2
    local ext_net=$3
    local member_vm=$4
    local test_tag=`uuidgen`
    local lb_name=test-lb-${test_tag}

    exists="`juju status --format=json| jq '.applications| to_entries[]| select(.value.charm| test(\".+octavia.+\"))'`"
    if [ -z "$exists" ]; then
        echo "INFO: no octavia found - skipping test"
        return 0
    fi

    if [ -n "$UA_OS_CHECKS_PROJECT_NET" ]; then
        net=$UA_OS_CHECKS_PROJECT_NET
    else
        read -p "Tenant network name to use for Octavia LB test: " net
    fi
    if [ -n "$UA_OS_CHECKS_PROJECT_SUBNET" ]; then
        subnet=$UA_OS_CHECKS_PROJECT_SUBNET
    else
        read -p "Tenant subnet name to use for Octavia LB test: " subnet
    fi
    if [ -n "$UA_OS_CHECKS_EXT_NET" ]; then
        ext_net=$UA_OS_CHECKS_EXT_NET
    else
        read -p "External net to use for Octavia LB test: " ext_net
    fi
    if [ -n "$UA_OS_CHECKS_VM_UUID" ]; then
        member_vm=$UA_OS_CHECKS_VM_UUID
    else
        read -p "UUID of guest vm with something listening on port 80 (e.g. apache): " member_vm
    fi

    lb_id=`openstack loadbalancer create --name $lb_name --vip-subnet-id $subnet -c id -f value`
    wait_cycle=0
    while true; do
        ((wait_cycle++ < MAX_WAIT_ACTIVE)) || { _delete_lb $lb_id; return 1; }
        status="`openstack loadbalancer show $lb_id -c provisioning_status -f value`"
        [ "$status" = "ACTIVE" ] && break
        [ "$status" = "ERROR" ] && { _delete_lb $lb_id; return 1; }
        echo "Waiting for LB $lb_name (uuid=$lb_id) to be ACTIVE (current=$status)"
    done
    openstack loadbalancer listener create --name test-listener-${test_tag} --protocol HTTP --protocol-port 80 $lb_id
    wait_cycle=0
    while true; do
        ((wait_cycle++ < MAX_WAIT_ACTIVE)) || { _delete_lb $lb_id; return 1; }
        status="`openstack loadbalancer listener show test-listener-${test_tag} -c provisioning_status -f value`"
        [ "$status" = "ACTIVE" ] && break
        [ "$status" = "ERROR" ] && { _delete_lb $lb_id; return 1; }
        echo "Waiting for Listener test-listener-${test_tag} to be ACTIVE (current=$status)"
    done
    openstack loadbalancer pool create --name test-pool-${test_tag} --lb-algorithm ROUND_ROBIN --listener test-listener-${test_tag} --protocol HTTP
    wait_cycle=0
    while true; do
        ((wait_cycle++ < MAX_WAIT_ACTIVE)) || { _delete_lb $lb_id; return 1; }
        status="`openstack loadbalancer pool show test-pool-${test_tag} -c provisioning_status -f value`"
        [ "$status"  = "ACTIVE" ] && break
        [ "$status" = "ERROR" ] && { _delete_lb $lb_id; return 1; }
        echo "Waiting for test-pool-${test_tag} to be ACTIVE (current=$status)"
    done
    openstack loadbalancer healthmonitor create --delay 5 --max-retries 4 --timeout 10 --type HTTP --url-path / test-pool-${test_tag}
    openstack loadbalancer healthmonitor list
    if [ -n "$member_vm" ]; then
        netaddr=$(openstack port list --server $member_vm --network $net \
                  -c "Fixed IP Addresses" -f value | sed -r "s/.*ip_address(=|':\s+)'([[:digit:]\.]+)'.*/\2/g")
        member_id=$(openstack loadbalancer member create --subnet-id $subnet \
                    --address $netaddr --protocol-port 80 --format value --column id test-pool-${test_tag})
        wait_cycle=0
        while true; do
            ((wait_cycle++ < MAX_WAIT_ACTIVE)) || { _delete_lb $lb_id; return 1; }
            status="`openstack loadbalancer member show -f value -c provisioning_status test-pool-${test_tag} $member_id`"
            [ "$status" = ACTIVE ] && break
            [ "$status" = "ERROR" ] && { _delete_lb $lb_id; return 1; }
            echo "Waiting for member $member_vm ($member_id) to be ACTIVE (current=$status)"
        done

        openstack loadbalancer member list test-pool-${test_tag}

        fip=`openstack floating ip create -f value -c floating_ip_address $ext_net`
        lb_vip_port_id=$(openstack loadbalancer show -f value -c vip_port_id $lb_id)
        openstack floating ip set --port $lb_vip_port_id $fip
        nc -w 5 -vz $fip 80
        rc=$?
    fi

    _delete_lb $lb_id

    # PASS
    return $rc
}

test_images_disk_format()
{
    # Checks to see if Ceph backend is used in either Nova or Cinder and if it
    # is, checks that all images in Glance have disk_format=raw.
    # See the following KB article for information on why this is important:
    # https://support.canonical.com/ua/s/article/openstack-boot-image-considerations

    local rc=0
    local ftmp=`mktemp`

    exists="`juju status --format=json| jq '.applications| to_entries[]| select(.value.charm| test(\".+ceph-mon.+\"))'`"
    if [ -z "$exists" ]; then
        echo "INFO: no ceph-mon found - skipping test"
        rm $ftmp
        return 0
    fi

    juju status ceph-mon --format=json > $ftmp
    readarray -t clients<<<"`jq -r '.applications."ceph-mon".relations.client[]' $ftmp`"
    if ((${#clients[@]})) && [ -n "${clients[0]}" ]; then
        raw_required=false
        for client in ${clients[@]}; do
            if [[ $client =~ nova-compute.* ]] ||
                   [[ $client =~ cinder-ceph.* ]]; then
                raw_required=true
                break
            fi
        done
        if $raw_required; then
            openstack image list --long -c ID -c 'Disk Format' -f value > $ftmp
            if ((`sort -u -k 2 $ftmp| wc -l` > 1)); then
cat << EOF
WARNING: not all images in Glance have disk_format=raw

Your environment is using Ceph as a backend for one or both of nova-compute
or cinder and as a result it is essential to use images with raw format in
order to avoid a large capacity and performance impact on your cloud and ceph
cluster. This format is also needed in order to benefit from Copy-on-Write
cloning of images in both Cinder and Nova.

For more information on why this is important please see the following article:

    https://support.canonical.com/ua/s/article/openstack-boot-image-considerations
EOF
                echo -e "\nImage format details:\n"
                readarray -t formats<<<"`sort -u -k 2 $ftmp| awk '{print $2}'`"
                for fmt in ${formats[@]}; do
                    awk "\$2==\"$fmt\" {print \$2}" $ftmp| sort| uniq -c
                done

                rc=1
            fi
        else
            echo "No hard requirement for raw images - skipping check"
        fi
    fi

    rm $ftmp
    return $rc
}


# Install dependencies
dpkg -s jq &>/dev/null || sudo apt install -y jq

## Run Tests
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

echo -e "\nRunning Glance image format test"
test_images_disk_format && \
    echo "Result: [PASS]" || echo "Result: [FAIL]"

echo -e "\nRunning Octavia LoadBalancer test"
test_octavia_lb && \
    echo "Result: [PASS]" || echo "Result: [FAIL]"

echo -e "\nDone."
