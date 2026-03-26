# Storage performance tests

These tests aim to test the performance of a Ceph cluster. They are organised
as jobs and classes where classes are basically readwrite definitions
(randread, readwrite etc) and jobs are the config for the test itself.
See --help for details on options.

# Running tests

You can a specific test like:

./run-tests.sh --name mytest --job 4m --class randwrite --yes

Or all tests with:

./run-tests.sh --name mytest --job all --class all --yes

The output is collected as a tarball.

## Running tests on Kubernetes

### Prerequisites
- A Kubernetes cluster with a ceph storage provisioner
- `kubectl` configured and pointing at your cluster

### Configure storage class
Edit `k8s-benchmark-job.yaml` and uncomment/set `storageClassName` to match your cluster:
```bash
kubectl get storageclass
```

### Configure tests to run (optional)
By default, the job runs all tests. You can edit line 32 in `k8s-benchmark-job.yaml` to run a specific test. For example:
```bash
./run-tests.sh --name mytest --job 4m --class randwrite --yes
```

### Create the ConfigMap
From the current directory (`storage/fio/`):
```bash
kubectl create configmap fio-config --from-file=run-tests.sh --from-file=conf/
```

### Deploy
```bash
kubectl apply -f k8s-benchmark-job.yaml
```

### Monitor
```bash
# Watch the pod start
kubectl get pods -l job-name=fio-benchmark -w

# Follow the test output
kubectl logs -f job/fio-benchmark
```

### Retrieve results
Find and copy the results tarball:
```bash
POD=$(kubectl get pods -l job-name=fio-benchmark -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD -- ls /data  
# Replace 'mytest-xxxx.tgz' with the name of your tarball
kubectl cp $POD:/data/mytest-xxxx.tgz ~/fio-test-results.tgz
```

### Cleanup
```bash
kubectl delete -f k8s-benchmark-job.yaml
kubectl delete configmap fio-config
```
