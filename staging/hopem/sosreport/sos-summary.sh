#!/bin/bash -eu
#
# Generate a high-level summary of a sosreport.
#
declare -a roots=()
ctg_selected=true
ctg_brief=true
ctg_versions=false
ctg_openstack=false
ctg_storage=false
ctg_juju=false
ctg_kernel=false
ctg_system=false
write_to_file=false

usage ()
{
cat << EOF
USAGE: xseg OPTIONS

OPTIONS
    -h|--help
        This message
    --juju
        Include Juju info
    --openstack
        Include Openstack services info
    --kernel
        Include Kernel info
    --storage
        Include storage info including Ceph
    --system
        Include system info
    --versions
        Include software version info
    -s|--save
    -a|--all
EOF
}

while (($#)); do 
    case $1 in
          -h|--help)
              usage
              exit 0
              ;;
          --versions)
              ctg_selected=true
              ctg_versions=true
              ;;
          --juju)
              ctg_selected=true
              ctg_juju=true
              ;;
          --openstack)
              ctg_selected=true
              ctg_openstack=true
              ;;
          --storage)
              ctg_selected=true
              ctg_storage=true
              ;;
          --kernel)
              ctg_selected=true
              ctg_kernel=true
              ;;
          --system)
              ctg_selected=true
              ctg_system=true
              ;;
          -s|--save)
              write_to_file=true
              ;;
          -a|--all)
            ctg_selected=false
              ;;
          *)
              roots+=( $1 )
              ;;
    esac
    shift
done

if ! $ctg_selected; then
    ctg_versions=true
    ctg_openstack=true
    ctg_storage=true
    ctg_juju=true
    ctg_kernel=true
    ctg_system=true
fi

f_output=`mktemp`

((${#roots[@]})) || roots=( . )

for root in ${roots[@]}; do

sosreport_name=`basename $root`

(

# TODO
#if false && [ "`file -b $root`" = "XZ compressed data" ]; then
#    dtmp=`mktemp -d`
#    tar --exclude='*/*' -tf $root
#    sosroot=`tar --exclude='*/*' -tf $root| sed -r 's,([[:alnum:]\-]+)/*.*,\1,g'| sort -u`
#    tar -tf $root $sosroot/var/log/juju 2>/dev/null > $dtmp/juju
#    if (($?==0)); then
#        mkdir -p $dtmp/var/log/juju
#        mv $dtmp/juju $dtmp/var/log/
#    fi
#    tree $dtmp
#    root=$dtmp
#fi

[ -z "$root" ] || cd $root

echo -e "## sosreport-summary ##\n" > $f_output

echo -e "hostname:\n  - `cat hostname`" >> $f_output
if $ctg_versions; then
    echo -e "versions:" >> $f_output
    echo -n "  - ubuntu: " >> $f_output
    sed -r 's/DISTRIB_CODENAME=(.+)/\1/g;t;d' etc/lsb-release >> $f_output

    echo -n "  - openstack: " >> $f_output
    apts='etc/apt/sources.list.d/*.list'
    if [ -d "`dirname \"$apts\"`" ] && `grep -qr ubuntu-cloud.archive $apts 2>/dev/null`; then
        ost_rel="`grep -r ubuntu-cloud.archive $apts| grep -v deb-src |\
            sed -r 's/.+-updates\/(.+)\s+.+/\1/g;t;d'`"
        [ -n "$ost_rel" ] || ost_rel=unknown
        echo "$ost_rel" >> $f_output
    else
        echo "distro" >> $f_output
    fi
fi

if $ctg_openstack; then
    echo -e "openstack:" >> $f_output

    # TODO: keep this list up-to-date with services we care about in the context of openstack
    declare -a services=(
    aodh
    apache
    barbican
    beam.smp
    ceilometer
    ceph
    cinder
    designate
    glance
    gnocchi
    heat
    horizon
    keystone
    mysqld
    neutron
    nova
    octavia
    openstack-dashboard
    rabbitmq-server
    rados
    swift
    vault
    qemu-system-x86_64
    )
    if [ -r "ps" ]; then
        declare -A openstack_info=()
        for svc in ${services[@]}; do
            readarray -t out<<<"`sed -r -e \"s/.+(${svc}[[:alnum:]\-]*)\s+.+/\1/g;t;d\" ps`"
            ((${#out[@]}==0)) || [ -z "${out[0]}" ] && continue
            for e in ${out[@]}; do
                n=${openstack_info[$e]:-0}
                openstack_info[$e]=$((n+1))
            done
        done
        if ((${#openstack_info[@]})); then
            for e in ${!openstack_info[@]}; do
                echo "  - $e (${openstack_info[$e]})"
            done| sort -k 2 >> $f_output
        else
            echo "  - null" >> $f_output
        fi
    else
        echo "  ps not found - skipping openstack service detection" >> $f_output
    fi
fi

if $ctg_storage; then
    echo -e "ceph:" >> $f_output

    services=(
    ceph-osd
    ceph-mon
    ceph-mgr
    radosgw
    )
    if [ -r "ps" ]; then
        hash=`md5sum $f_output`
        ( for svc in ${services[@]}; do
            out="`sed -r \"s/.*(${svc}[[:alnum:]\-]*)\s+.+/\1/g;t;d\" ps| sort| uniq| sed -r 's/^\s+/  /g'`"
            id="`sed -r \"s/.*(${svc}[[:alnum:]\-]*)\s+.+--id\s+([[:digit:]]+)\s+.+/\2/g;t;d\" ps| tr -s '\n' ','| sort| sed -r -e 's/^\s+/  /g' -e 's/,$//g'`"
            [ -z "$out" ] && continue
            echo "  - $out ($id)"
        done ) >> $f_output
        [ "$hash" = "`md5sum $f_output`" ] && echo "  - null" >> $f_output
    else
        echo "  ps not found - skipping ceph service detection" >> $f_output
    fi
    
    echo "bcache-info:" >> $f_output
    readarray -t bcacheinfo<<<"`grep . sos_commands/block/ls_-lanR_.sys.block| egrep 'bcache|nvme'| sed -r 's/.+[[:digit:]\:]+\s+([[:alnum:]]+)\s+.+/\1/g'`"
    ((${#bcacheinfo[@]})) || bcacheinfo=( "null" )
    block_root=sos_commands/block/udevadm_info_.dev.
    for out in ${bcacheinfo[@]}; do
        if [ -e "${block_root}$out" ]; then
            echo "/dev/$out (`grep ' disk/by-dname' ${block_root}$out| sed -r 's,.+/(.+),\1,g'`)"
        else
            echo $out
        fi
    done| xargs -l -I{} echo "  - {}" >> $f_output
fi

if $ctg_juju; then
    if [ -d "var/log/juju" ]; then
        echo -e "juju-units:" >> $f_output

        readarray -t ps_units<<<"`egrep unit-\* ps| sed -r 's,.+unit-([[:alpha:]\-]+-[[:digit:]]+).*,\1,g;t;d'| sort -u`"
        readarray -t log_units<<<"`find var/log/juju -name unit-\*| sed -r 's,.+unit-([[:alpha:]\-]+-[[:digit:]]+).*.log.*,\1,g;t;d'| sort -u`"

        declare -a juju_info_local=()
        declare -a juju_info_nonlocal=()
        
        for unit in ${ps_units[@]}; do
            if `echo "${log_units[@]}"| egrep -q "\s?${unit}\s?"`; then
                juju_info_local+=( "${unit}\n" )
            else
                juju_info_nonlocal+=( "${unit}\n" )
            fi
        done

        if (("${#ps_units[@]}"==0)) || [ -z "${ps_units[0]}" ]; then
            echo -e "juju-units:" >> $f_output
            echo "  - null" >> $f_output
        else
            echo -e "  local:" >> $f_output
            echo -e ${juju_info_local[@]}| sort -u| xargs -l -I{} echo "  - {}" >> $f_output
            echo -e "  non-local (e.g. lxd):" >> $f_output
            if (("${#juju_info_nonlocal[@]}"==0)) || [ -z "${juju_info_nonlocal[0]}" ]; then
                juju_info_nonlocal=( null )
            fi
            echo -e ${juju_info_nonlocal[@]}| sort -u| xargs -l -I{} echo "  - {}" >> $f_output
        fi
    fi
fi

if $ctg_system; then
echo -e "system:" >> $f_output
sed -r 's/.+(load average:.+)/- \1/g' uptime|xargs -l -I{} echo "  {}" >> $f_output
echo "  - rootfs: `egrep ' /$' df`" >> $f_output
fi

if $ctg_kernel; then
    echo -e "kernel:" >> $f_output
    path=proc/cmdline
    if [ -e "$path" ]; then
        cat $path|xargs -l -I{} echo "  - {}" >> $f_output
    else
        echo "  - $path not found" >> $f_output
    fi

    echo -e "systemd:" >> $f_output
    path=sos_commands/systemd/systemctl_show_service_--all
    if [ -e "$path" ]; then
        if `egrep -q "CPUAffinity=.+" $path`; then
            egrep "CPUAffinity=.+" $path| sort -u|xargs -l -I{} echo "  - {}"  >> $f_output
        else
            echo "  - CPUAffinity not set"  >> $f_output
        fi
    else
        echo "  - $path not found" >> $f_output
    fi
fi

)

if $write_to_file; then
    out=${sosreport_name}.summary
    mv $f_output $out
    echo "Summary written to $out"
else
    cat $f_output
    echo ""
    rm $f_output
fi

echo "INFO: see --help for more display options"

done
