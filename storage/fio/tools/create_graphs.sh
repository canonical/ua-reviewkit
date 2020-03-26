#!/bin/bash -eu
path=$1

[ -e "$1" ] || { echo "ERROR: invalid path $1 - need path to fio test results"; exit 1; }

needed=( fio gnuplot )
not_installed=()
for p in ${needed[@]}; do
    dpkg -s $p &>/dev/null || not_installed+=( $p )
done
if ((${#not_installed[@]})); then
    read -p "Ok to install the following packages?: ${not_installed[@]} [Y/n]" answer
    [ "${answer,,}" = "y" ] || [ -z "$answer" ] && sudo apt install -y ${not_installed[@]} || true
fi
for d in `find $path/* -type d`; do (cd $d; echo $d ; fio2gnuplot -p '*log' -g;); done

echo "Done."
