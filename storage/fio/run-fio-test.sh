#!/bin/bash -eu
TESTNAME=fio-perf-test
JOBDIR_PREFIX=`date +%s`
OPT_DRY_RUN=false

readarray -t TEST_JOBS<<<"`ls conf| sed -r 's/^(.+)\.fio\.template$/\1/g;t;d'| grep -v global`"
readarray -t TEST_CLASSES<<<"`ls conf| sed -r 's/^(.+)-global\.fio\.template$/\1/g;t;d'`"

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
`echo "${TEST_JOBS[@]}"| xargs -l -I{} echo -e "\t - {}"`

        If no job is specified then all will be run.
    --class
        Test class to run, Available options are:
`echo "${TEST_CLASSES[@]}"| xargs -l -I{} echo -e "\t - {}"`

        If no class is specified then all will be run.
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
        --job)
           TEST_JOBS=( "$2" )
           shift
           ;;
        --class)
           TEST_CLASSES=( "$2" )
           shift
           ;;
        -l|--label)
           JOBDIR_PREFIX="$2"
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

answer=y
((${#TEST_CLASSES[@]} == 1)) || read -p "No class specified so running all - OK? [y/N]" answer
[ "${answer,,}" = "y" ] || { echo "Aborting."; exit; }
((${#TEST_JOBS[@]} == 1)) || read -p "No job specified so running all - OK? [y/N]" answer
[ "${answer,,}" = "y" ] || { echo "Aborting."; exit; }

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
