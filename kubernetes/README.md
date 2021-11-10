----- GETTING STARTED ------

Sonobuoy depends on kubernetes version that is being used.
As per documentation, each version of sonobuoy will cover that
same k8s version and two older versions (e.g. v0.14.X covers
k8s 1.14, 1.13 and 1.12).

Check your kubernetes version with:

$ kubectl version --short=true
Client Version: v1.19.4
Server Version: v1.19.4  <-------

Based on that version, check out which is the corresponding
sonobuoy available on:
https://github.com/vmware-tanzu/sonobuoy/releases/

Once the version was found, run the following command, as
the example below:

$ SONOBUOY_VERSION=0.19.0 ./kubernetes-extra-checks.sh

While tests are running, follow logs on sonobuoy's pod:

$ kubectl logs -f -n sonobuoy <sonobuoy-job-name> e2e

