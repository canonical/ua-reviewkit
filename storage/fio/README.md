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
