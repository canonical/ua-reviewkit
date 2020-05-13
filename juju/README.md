# UA Juju Bundle Verification

This tool applies checks to a bundle to verify that UA handover compatibility
is met by looking for known issues.

# Running the tool

All checks to be carried out are defined under the checks directory and are
categorised based on the type of deployment being checked.

There are two ways to run the tool;

The tool will check the contents of a Juju bundle based on the checks file
provided. The type of checks file used is selected with the --type option. By
default the tool will look for bundle.yaml under the path provided by
--fce-config. You can override the bundle name with --bundle e.g.

ua-bundle-check.py --fce-config <path to cpe-deployments config directory>

or

ua-bundle-check.py --fce-config <path to cpe-deployments config directory> --bundle <filename>

For environments that do not have fce config you can just provide the path to a
bundle with --bundle and any checks that would have required fce data will be
skipped with warning e.g.

ua-bundle-checker.py --bundle <path to bundle>


Results are logged in a file that can be used to share results.

