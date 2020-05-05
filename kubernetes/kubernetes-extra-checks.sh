#!/bin/bash -ex

SONOBUOY_VERSION=${SONOBUOY_VERSION:-0.18.0}
SONOBUOY_PARALLEL=${SONOBUOY_PARALLEL:-30}

function fetch_sonobuoy() {
    rm -rf sonobuoy.*
    wget https://github.com/vmware-tanzu/sonobuoy/releases/download/v"$SONOBUOY_VERSION"/sonobuoy_"$SONOBUOY_VERSION"_linux_amd64.tar.gz
    tar xvf sonobuoy_"$SONOBUOY_VERSION"_linux_amd64.tar.gz
}

function  run_sonobuoy() {
  if [[ ! -x "./sonobuoy" ]]; then
    fetch_sonobuoy
  fi

  ./sonobuoy delete --all || true
  ./sonobuoy run --skip-preflight --plugin e2e --e2e-parallel ${SONOBUOY_PARALLEL} --mode=non-disruptive-conformance --wait 2>&1
  ./sonobuoy results $(./sonobuoy retrieve) -m dump | ./parse_results.py failed
}

function main() {
  run_sonobuoy
}

main