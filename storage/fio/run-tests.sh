#!/bin/bash -eu
TESTNAME=fio-perf-test
JOBDIR_PREFIX=`date +%s`
OPT_DRY_RUN=false
FORCE_YES=false
NO_CLEANUP=false
WILDCARD="all"
NO_TARBALL=false
declare -a TEST_JOBS=()
declare -a TEST_CLASSES=()

declare -A CUSTOM_JOB_OPTS=(
    [--blocksize]=
    [--iodepth]=
    [--size]=
    [--fdatasync]=
    [--ioengine]=
    [--direct]=
)

readarray AVAILABLE_JOBS<<<"`ls conf| sed -r 's/^(.+)\.fio\.template$/\1/g;t;d'| egrep -v 'global|custom'`"
readarray AVAILABLE_CLASSES<<<"`ls conf| sed -r 's/^(.+)-global\.fio\.template$/\1/g;t;d'| egrep -v 'common'`"

usage ()
{
cat << EOF
USAGE: `basename $0` OPTIONS

    Run a set of pre-configured fio test jobs. Results are collected into a
    tarball.

OPTIONS:
    --blocksize
        Custom blocksize. If this is provided you also need to provide an
        iodepth with --iodepth. This overrides --job.
    --class
        Test class to run, Available options are:
`echo "${AVAILABLE_CLASSES[@]}"| xargs -l -I{} echo -e "\t - {}"`

        Can be specified multiple times.

        If no class is specified then all will be run. If you want avoid being
        asked for confirmation that you mean all then set this to "all".
    --dry-run
        Do not execute the test. Will generate the config and print the command.
    -h|--help
        Prints this message
    --iodepth
        Custom iodepth. If this is provided you also need to provide a
        blocksize with --blocksize. This overrides --job.
    --job
        Test job to run, Available options are:
`echo "${AVAILABLE_JOBS[@]}"| xargs -l -I{} echo -e "\t - {}"`

        Can be specified multiple times.

        If no job is specified then all will be run. If you want avoid being
        asked for confirmation that you mean all then set this to "all".
    -l|--label
        Job label. Will use 'date +%s' if not provided.
    -n|--name
        Name for test run used to identify results. Defaults to $TESTNAME.
    --no-cleanup
        Don't delete the fio IO file after tests. This is done by default to
        avoid running out of space for future tests.
    --no-tarball
        Do not create a tarball.
    --yes
        Run tests non-interactively.

EOF
}

while (($#)); do
    case $1 in
        --dry-run)
            OPT_DRY_RUN=true
            ;;
        --blocksize|--iodepth|--fdatasync|--size|--ioengine|--direct)
            CUSTOM_JOB_OPTS[$1]=$2
            shift
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
        --no-tarball)
            NO_TARBALL=true
            ;;
        -n|--name)
            TESTNAME="$2"
            shift
            ;;
        *)
            echo "ERROR: unknown option '$1'"
            exit 1
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

in_array ()
{
    key=$1
    shift
    while (($#)); do [ "$key" = "$1" ] && return 0 || shift; done
    return 1
}

has_custom_job_opts ()
{
    for opt in ${!CUSTOM_JOB_OPTS[@]}; do
        [ -z "${CUSTOM_JOB_OPTS[$opt]}" ] || return 0
    done
    return 1
}

answer=y
if ((${#TEST_CLASSES[@]}==0)); then
    read -p "All classes (${#AVAILABLE_CLASSES[@]}) will be run - OK? (use '--class $WILDCARD' to avoid this message) [y/N] " answer
    [ "${answer,,}" = "y" ] || { echo "Aborting."; exit; }
else
    for c in ${TEST_CLASSES[@]}; do
        `in_array "$c" ${AVAILABLE_CLASSES[@]}` && continue || true
        [ "$c" = "$WILDCARD" ] && continue || true
        echo "ERROR: unknown class '$c'"
        exit 1
    done
fi

if ((${#TEST_JOBS[@]}==0)) && ! has_custom_job_opts; then
    read -p "All jobs (${#AVAILABLE_JOBS[@]}) will be run - OK? (use '--job $WILDCARD' to avoid this message) [y/N] " answer
    [ "${answer,,}" = "y" ] || { echo "Aborting."; exit; }
else
    for j in ${TEST_JOBS[@]}; do
        `in_array "$j" ${AVAILABLE_JOBS[@]}` && continue || true
        [ "$j" = "$WILDCARD" ] && continue || true
        echo "ERROR: unknown job '$j'"
        exit 1
    done
fi
# custom jobs can be added to the existing job list (which can be empty if custom is available)
if has_custom_job_opts; then
    for opt in ${!CUSTOM_JOB_OPTS[@]}; do
        [ -n "${CUSTOM_JOB_OPTS[$opt]}" ] || { echo "ERROR: please provide $opt"; exit 1; }
    done
    TEST_JOBS+=( custom )
fi

{ ((${#TEST_CLASSES[@]}==0)) || [ "${TEST_CLASSES[0]}" = "$WILDCARD" ]; } && TEST_CLASSES=( ${AVAILABLE_CLASSES[@]} )
{ ((${#TEST_JOBS[@]}==0)) || [ "${TEST_JOBS[0]}" = "$WILDCARD" ]; } && TEST_JOBS=( ${AVAILABLE_JOBS[@]} )

results_dir=${TESTNAME}-${JOBDIR_PREFIX}
mkdir $results_dir
mkdir -p $results_dir/iofiles
logfile=`pwd`/$results_dir/${TESTNAME}-${JOBDIR_PREFIX}.log
echo "Logging to $logfile"
for class in ${TEST_CLASSES[@]}; do
    global=${class}-global.fio.template
    for job in ${TEST_JOBS[@]}; do
        job_template=${job}.fio.template
        joblabel=$class-$job
        jobdir=${joblabel}.results
        mkdir $results_dir/$jobdir

        config=${class}-${job}.fio
        cat conf/$global > $results_dir/$jobdir/$config
        cat conf/$job_template >> $results_dir/$jobdir/$config

        if has_custom_job_opts; then
            sed -r -i "s/__BLOCKSIZE__/${CUSTOM_JOB_OPTS[--blocksize]}/g" $results_dir/$jobdir/$config
            sed -r -i "s/__IODEPTH__/${CUSTOM_JOB_OPTS[--iodepth]}/g" $results_dir/$jobdir/$config
            sed -r -i "s/__SIZE__/${CUSTOM_JOB_OPTS[--size]}/g" $results_dir/$jobdir/$config
            sed -r -i "s/__FDATASYNC__/${CUSTOM_JOB_OPTS[--fdatasync]}/g" $results_dir/$jobdir/$config
            sed -r -i "s/__IOENGINE__/${CUSTOM_JOB_OPTS[--ioengine]}/g" $results_dir/$jobdir/$config
            sed -r -i "s/__DIRECT__/${CUSTOM_JOB_OPTS[--direct]}/g" $results_dir/$jobdir/$config
        fi

        sed -r -i "s/__TESTNAME__/$TESTNAME/g" $results_dir/$jobdir/$config

        # copy common global config into job dir
        cp conf/common-global.fio.template $results_dir/$jobdir/common-global.fio
        sed -r -i "s/__TESTNAME__/${TESTNAME}-${JOBDIR_PREFIX}/g" $results_dir/$jobdir/common-global.fio

        header $TESTNAME $job $jobdir | tee -a $logfile
        (
            cd $results_dir/$jobdir
            if $OPT_DRY_RUN; then
                echo "## DRY-RUN ##"
                echo "fio $config --write_lat_log=$joblabel --write_bw_log=$joblabel --write_iops_log=$joblabel"
                # delete io file to avoid running out of space for subsequent runs.
            else
                $FORCE_YES || read -p "Run test? [Y/n]" answer
                if [ -z "$answer" ] || [ "${answer,,}" = "y" ]; then
                    fio $config --write_lat_log=$joblabel --write_bw_log=$joblabel --write_iops_log=$joblabel
                else
                    echo -e "\n# Test Not Run #"
                fi
            fi
        ) | tee -a $logfile
        footer | tee -a $logfile
    done
done
$NO_CLEANUP || rm -rf $results_dir/iofiles

if ! $NO_TARBALL && ! $OPT_DRY_RUN; then
    tar -czf ${results_dir}.tgz $results_dir
    echo "Results tarball '${results_dir}.tgz' created."
fi

echo "Done."
