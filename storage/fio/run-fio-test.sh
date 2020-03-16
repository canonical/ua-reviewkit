#!/bin/bash -eu
TESTNAME=fio-perf-test
JOBDIR_PREFIX=`date +%s`
OPT_DRY_RUN=false
FORCE_YES=false
NO_CLEANUP=false
declare -a TEST_JOBS=()
declare -a TEST_CLASSES=()

readarray _TEST_JOBS<<<"`ls conf| sed -r 's/^(.+)\.fio\.template$/\1/g;t;d'| grep -v global`"
readarray _TEST_CLASSES<<<"`ls conf| sed -r 's/^(.+)-global\.fio\.template$/\1/g;t;d'| egrep -v 'common'`"

usage ()
{
cat << EOF
USAGE: `basename $0` OPTIONS TEST

OPTIONS:
    -h|--help
        Prints this message
    -l|--label
        Job label. Will use timestamp if not provided.
    --job
        Test job to run, Available options are:
`echo "${_TEST_JOBS[@]}"| xargs -l -I{} echo -e "\t - {}"`

        Can be specified multiple times.

        If no job is specified then all will be run. If you want avoid being
        asked for confirmation that you mean all then set this to "all".
    --class
        Test class to run, Available options are:
`echo "${_TEST_CLASSES[@]}"| xargs -l -I{} echo -e "\t - {}"`

        Can be specified multiple times.

        If no class is specified then all will be run. If you want avoid being
        asked for confirmation that you mean all then set this to "all".
    --dry-run
        Do not execute the test. Will generate the config and print the command.
    --yes
        Run tests non-interactively.
    --no-cleanup
        Don't delete the fio IO file after tests. This is done by default to
        avoid running out of space for future tests.

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
        --job)
            TEST_JOBS+=( "$2" )
            shift
            ;;
        --class)
            TEST_CLASSES+=( "$2" )
            shift
            ;;
        -l|--label)
            JOBDIR_PREFIX="$2"
            shift
            ;;
        --yes)
            FORCE_YES=true
            ;;
        --no-cleanup)
            NO_CLEANUP=true
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

answer=y
if ((${#TEST_CLASSES[@]}==0)); then
    read -p "All classes (${#_TEST_CLASSES[@]}) will be run - OK? (use '--job all' to avoid this message) [y/N] " answer
fi
[ "${answer,,}" = "y" ] || { echo "Aborting."; exit; }
if ((${#TEST_JOBS[@]}==0)); then
    read -p "All jobs (${#_TEST_JOBS[@]}) will be run - OK? (use '--class all' to avoid this message) [y/N] " answer
fi
[ "${answer,,}" = "y" ] || { echo "Aborting."; exit; }

{ ((${#TEST_CLASSES[@]}==0)) || [ "${TEST_CLASSES[0]}" = "all" ]; } && TEST_CLASSES=( ${_TEST_CLASSES[@]} )
{ ((${#TEST_JOBS[@]}==0)) || [ "${TEST_JOBS[0]}" = "all" ]; } && TEST_JOBS=( ${_TEST_JOBS[@]} )


logfile=`pwd`/${TESTNAME}-${JOBDIR_PREFIX}.log
echo "Logging to $logfile"
for class in ${TEST_CLASSES[@]}; do
    global=${class}-global.fio.template
    for job in ${TEST_JOBS[@]}; do
        job_template=${job}.fio.template
        joblabel=${TESTNAME}-${JOBDIR_PREFIX}-$class-$job
        jobdir=${joblabel}.results
        mkdir $jobdir

        config=${class}-${job}.fio
        cat conf/$global > $jobdir/$config
        cat conf/$job_template >> $jobdir/$config
        sed -r -i "s/__TESTNAME__/$TESTNAME/g" $jobdir/$config
        # copy common global config into job dir
        cp conf/common-global.fio.template $jobdir/common-global.fio

        header $TESTNAME $job $jobdir | tee -a $logfile
        (
            cd $jobdir
            echo "Running test: $config"
            cat $config
            if $OPT_DRY_RUN; then
                echo "## DRY-RUN ##"
                echo "fio $config --write_lat_log=$joblabel --write_bw_log=$joblabel --write_iops_log=$joblabel"
                # delete io file to avoid running out of space for subsequent runs.
            else
                $FORCE_YES || read -p "Run test? [Y/n]" answer
                [ "${answer,,}" = "n" ] || \
                    fio $config --write_lat_log=$joblabel --write_bw_log=$joblabel --write_iops_log=$joblabel
                $NO_CLEANUP || rm -f ${job}.0.0
            fi
        ) | tee -a $logfile
        footer | tee -a $logfile
done

done
