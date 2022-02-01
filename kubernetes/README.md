----- GETTING STARTED ------

Sonobuoy can be executed by running the following command

```
$ ./kubernetes-extra-checks.sh
```

The above command by default
* uses latest sonobuoy release and
* retrieves the kubernetes version with:

```
$ kubectl version --short=true
Client Version: v1.23.3
Server Version: v1.23.3  <-------
```

Alternatively, user can specify sonobuoy and kubernetes
version as environment variables. 

Example of the command to run:

```
$ SONOBUOY_VERSION=0.56.0 K8S_VERSION=1.23.3 ./kubernetes-extra-checks.sh
```

While tests are running, follow logs on sonobuoy's pod:

```
$ kubectl logs -f -n sonobuoy <sonobuoy-job-name> e2e
```
