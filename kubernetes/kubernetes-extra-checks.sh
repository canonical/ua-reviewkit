#!/bin/bash -ex

K8S_VERSION=${K8S_VERSION:-1.21.0}
SONOBUOY_VERSION=${SONOBUOY_VERSION:-0.55.0}
SONOBUOY_PARALLEL=${SONOBUOY_PARALLEL:-30}
SONOBUOY_MODE=${SONOBUOY_MODE:-non-disruptive-conformance}
SONOBUOY_CONFORMANCE_IMAGE=${SONOBUOY_CONFORMANCE_IMAGE:-k8s.gcr.io/conformance:v${K8S_VERSION}}

function fetch_sonobuoy() {
    rm -rf sonobuoy.*
    wget https://github.com/vmware-tanzu/sonobuoy/releases/download/v"$SONOBUOY_VERSION"/sonobuoy_"$SONOBUOY_VERSION"_linux_amd64.tar.gz
    tar xvf sonobuoy_"$SONOBUOY_VERSION"_linux_amd64.tar.gz
}

function  cleanup() {
   test -x "./sonobuoy" && ./sonobuoy delete --all --wait
   exit 0
}

function  run_sonobuoy() {
  if [[ ! -x "./sonobuoy" ]]; then
    fetch_sonobuoy
  fi

  ./sonobuoy run --kube-conformance-image=${SONOBUOY_CONFORMANCE_IMAGE} --mode=${SONOBUOY_MODE} --skip-preflight --plugin e2e --e2e-parallel ${SONOBUOY_PARALLEL} --sonobuoy-image projects.registry.vmware.com/sonobuoy/sonobuoy:v${SONOBUOY_VERSION} --wait 2>&1
  ./sonobuoy results $(./sonobuoy retrieve) -m dump | ./parse_results.py failed
}

function main() {
  run_sonobuoy
  exit 0
}

trap cleanup EXIT

main
