# Openstack Extra Checks

This directory contains tools that provide checks to aspects of Openstack
deployments that might not be covered by existing tests.

To run the checks you must provide the full path to a credentials file:

   openstack-extra-checks.sh /path/to/openrc

You can then run the checks in two different ways:

1. run openstack-extra-checks.sh with no extra args and it will ask for input where required

2. run with some global variables pre-set e.g.

    # Octavia test requirements (if applicable)
    export UA_OS_CHECKS_PROJECT_NET=<tenant network name or uuid>
    export UA_OS_CHECKS_PROJECT_SUBNET=<tenant subnet name or uuid>
    export UA_OS_CHECKS_EXT_NET=<external net name or uuid>
    export UA_OS_CHECKS_VM_UUID=<vm uuid>

    The UA_OS_CHECKS_VM_UUID must be ACTIVE and have something listening on port 80 e.g.
    apache2 so that it can be used for a loadbalancer test.


IMPORTANT: please ensure when you run this that you have the correct Juju model selected. Most deployments will have e.g. a controller model, LMA model and an Openstack model (plus others). You will need to be sure that your openstack model is selected before running these tests e.g.

  * juju list-models
  * juju switch <model-name>
