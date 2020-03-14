#!/bin/bash -eu
TESTNAME=fio-perf-test
jobdir_PREFIX=`date +%s`
OPT_DRY_RUN=false
declare -a TEST_CLASSES=( randwrite )
declare -a TEST_JOBS=( 4k 512k )

usage ()
{
cat << EOF
USAGE: `basename $0` OPTIONS TEST

OPTIONS:
    -l|--label
        Job label. Will use timestamp if not provided.

    -h|--help
        Prints this message

    --dry-run
        Do not execute the test. Will generate the config and print the command.

TEST:
    Name of test to run. Must correspond to existing configs
    in conf directory. Defaults to $TESTNAME.

EOF
}

while (($#)); do
    case $1 in
        --dry-run)
           OPT_DRY_RUN=true
           ;;
        -h|--help)
           usage
           exit 0
           ;;
        -l|--label)
           jobdir_PREFIX="$2"
           shift
           ;;
        *)
           TESTNAME="$1"
           shift
           ;;
    esac
    shift
done

header ()
{
cat << EOF
###########################################################
#
#  Running test='$1' job='$2'
#  Results dir: $3
#
###########################################################
EOF
}

footer ()
{
cat << EOF

EOF
}


for class in ${TEST_CLASSES[@]}; do
    global=${class}-global.fio.template
    for job in ${TEST_JOBS[@]}; do
        job=${job}.fio.template
        joblabel=${TESTNAME}-${jobdir_PREFIX}-$job
        jobdir=${joblabel}.results
        mkdir $jobdir

        config=${class}-${job}.fio
        cat conf/$global > $jobdir/$config
        cat conf/$job >> $jobdir/$config
        sed -r -i "s/__TESTNAME__/$TESTNAME/g" $jobdir/$config

        header $TESTNAME $job $jobdir
        (
            cd $jobdir
            echo "Running test: $config"
            cat $config
            if $OPT_DRY_RUN; then
                echo "## DRY-RUN ##"
                echo "fio $config --write_lat_log=$joblabel --write_bw_log=$joblabel --write_iops_log=$joblabel"
            else
                read -p "Run test? [Y/n]" answer
                [ "${answer,,}" = "n" ] || \
                    fio $config --write_lat_log=$joblabel --write_bw_log=$joblabel --write_iops_log=$joblabel
            fi
        )
        footer
done

done
