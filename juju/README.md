# UA Juju Bundle Verification

This tool takes as input a Juju bundle and Foundation Cloud Engine
deployment configuration and runs through the bundle applying checks to charm
config based on pre-defined assertions. These checks are defined as assertions
on application config and are categorised by the type of deployment i.e.
Openstack, Kuberenetes etc and maintained as open source that anyone can
contribute to them.

All checks applied are defined in yaml and found in the checks directory. To
add or modify checks it should generally only be necessary to modify the yaml
but a new check requires an unsupported method, that will need to be added to
the AssertionHelpers class in ua-bundle-check.py.

# Running the tool

The first thing to do is decide what type of bundle it is. The default is
"openstack" but you can also have e.g. "kubernetes" or "osm" and those are
set use --type.

Then you can either provide a path to an fce config (lp:cpe-deployments) and
an optional bundle name override or just a bundle path - useful in scenarios
where a deployment may not have an associated fce config dir.

The tool will then check the contents of a Juju bundle based on the checks file
selected using --type.

By default the tool will look for bundle.yaml under the --fce-config path
provided. You can override this by providing a bundle name with --bundle e.g.

```
ua-bundle-check.py --fce-config <path to cpe-deployments config directory>
```

or

```
ua-bundle-check.py --fce-config <path to cpe-deployments config directory> --bundle <filename>
```

NOTE: the --fce-config path must point to the config dir in a local clone of
lp:cpe-deployments with the correct branch checked out. At some point we will
add support for providing a url so that there is no need to clone.

For environments that do not have fce config you can just provide the path to a
bundle with --bundle and any checks that would have required fce data will be
skipped with warning e.g.

```
ua-bundle-check.py --bundle <path to bundle>
```

Results are logged in a file that can be used to share results.
