# UA Deployment Verification Tools

## UA Juju Bundle Verification

This tool takes as input a Juju bundle file and Foundation Cloud Engine
deployment configuration and runs through the bundle applying checks e.g. to
charm config, based on pre-defined assertions.

Checks can be applied to charm config or application settings and are
categorised by the type of deployment i.e. Openstack, Kubernetes etc and
maintained as open-source so that anyone can contribute to them (see
CONTRIBUTING.md for more info).

All checks applied are defined in yaml and found in the checks directory. To
add or modify checks it should generally only be necessary to modify the yaml
but if a check requires a method that is not yet defined in the tool, that will
need to be added to the AssertionHelpers class in ua-bundle-check.py.

### Running the tool

The first thing to do is decide what type of deployment you are testing. This
can currently be one of "openstack", "kubernetes" or "osm" and those are set
use --type (default is openstack).

Then you must provide a path to your Juju bundle file and a path to your FCE
config which is used in the case where checks want to cross-reference hardware
config information.

If no bundle is provided with --bundle the tool will look for a file called
bundle.yaml under the --fce-config path but it is best to export a bundle from
your deployment so as to ensure what you are checking is what you have deployed
(and catch any changes make post-deployment). To do this you can do:

```
juju export-bundle > mybundle.yaml
ua-bundle-check.py --fce-config /path/to/cpe-deployments/config -b mybundle
```

The tool will then check the contents of your Juju bundle based on the selected
checks file.

NOTE: the --fce-config path must point to the config dir that was used to
deploy your environment and therefore must correspond to the configuration of
your infrastructure.


See --help for usage info.

Results are logged in a file that can be used to share results.

## UA HotSOS collector

This tool collects hotsos information from a running juju deployment. It logs
into the available machines, installs and runs the hotsos collect command.
The results are then collected and stored in a tarball. After the collection,
the tool will clean up any installed package from the machines.

### Running the tool

By default, the tool will collect hotsos from 1 unit for each application.
Calling the tool without any parameters will in most cases be enough:

```sh
hotsos-collector.py
```

See --help for usage info and more options.