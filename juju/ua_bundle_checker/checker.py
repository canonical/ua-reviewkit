#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Authors:
#  - edward.hope-morley@canonical.com

import os
import sys

from dataclasses import dataclass

import argparse
import datetime
import hashlib
import re
import yaml

from ua_bundle_checker.assertion.commands import (
    AssertionAssertChannel,
    CheckResult,
    CHARM_REGEX_TEMPLATE,
    LocalAssertionHelpers,
    ASSERTIONS,
)

HEADER_TEMPLATE = "=" * 80 + """
UA Juju bundle config verification
 * {}
 * type={}
 * bundle={}
 * bundle_sha1={}
 * assertions_sha1={}
""" + "=" * 80

OUT = None


class BundleCheckerError(Exception):
    """ Raised when an error occurs while checking a bundle. """


class OutputManager:
    """ Manage output directed at a file and/or stdout. """

    def __init__(self, logfile, verbose=False):
        self.logfile = logfile
        self.verbose = verbose

    def setup(self):
        if os.path.exists(self.logfile):
            os.unlink(self.logfile)

        global OUT  # pylint: disable=global-statement
        OUT = self

    def print(self, entry, stdout=False):
        if self.verbose or stdout:
            print(entry)

        with open(self.logfile, 'a', encoding='utf-8') as fd:
            if hasattr(entry, 'unformatted'):
                entry = entry.unformatted()

            fd.write(f"{entry}\n")


@dataclass
class UABundleCheckerParams:
    """ Parameters for the UABundleChecker """
    bundle_apps: dict
    charm_regex: str
    assertions: dict
    fce_config: str
    errors_only: bool = False


@dataclass
class AssertionContext:
    """ Assertion context """
    application: str
    opt: str
    method: str
    settings: dict


class UABundleChecker:
    """ Bundle checker used to apply assertions to a bundle. """

    def __init__(self, params):
        self.params = params
        self.applications = []
        self.charm_name = None
        self.results = {}

    def show_results(self):
        if not self.results:
            return

        for app, results in self.results.items():
            if (self.params.errors_only and
                    set(results.keys()) == set(["PASS"])):
                continue

            OUT.print(f"=> application '{app}'")
            for category in results:
                if self.params.errors_only and category == "PASS":
                    continue

                for result in results[category]:
                    OUT.print(result)

    def get_results_summary(self):
        summary = {}
        for results in self.results.values():
            for category in results:
                if category in summary:
                    summary[category] += len(results[category])
                else:
                    summary[category] = len(results[category])

        return summary

    def add_result(self, app_name, result):
        if app_name not in self.results:
            self.results[app_name] = {}

        results = self.results[app_name]
        if result.rc_str in results:
            results[result.rc_str].append(result)
        else:
            results[result.rc_str] = [result]

    def run_app_assertions(self, app, override_results=None,
                           overrides_only=False):
        """
        Run assertions for an application.

        @param name: application name
        @param overrides_only: If the application has assertion methods that
                               are overrides i.e. if
                               any one passes it supersedes all others,
                               process those first and mark them so that they
                               don't get executed again.
        @param override_results: dict of results indicating options that have
                                 an override which we don't need to process
                                 further.
        """
        override_methods = [method for method, runner in ASSERTIONS.items()
                            if runner.IS_OVERRIDE]
        results = {}

        for opt in self.params.assertions:
            if override_results and any(override_results.get(opt,
                                                             {}).values()):
                continue

            assertions = self.params.assertions[opt]
            if not assertions:
                continue

            for method, settings in assertions.items():
                if overrides_only and method not in override_methods:
                    continue

                if override_results and method in override_results.get(opt,
                                                                       {}):
                    continue

                if opt not in results:
                    results[opt] = {method: False}

                if settings is None:
                    settings = {}

                context = AssertionContext(app, opt, method, settings)
                if overrides_only:
                    results[opt][method] = self.run(context,
                                                    allow_missing=True,
                                                    ignore_fails=True)
                else:
                    results[opt][method] = self.run(context)

                if not results[opt][method] and not overrides_only:
                    # stop at the first failure
                    break

        return results

    def run_assertions(self):
        """ Run assertions for all applications. """
        if not self.has_charm_matches():
            return

        for app in self.applications:
            if not self.params.assertions:
                self.add_result(app,
                                CheckResult(CheckResult.FAIL,
                                            reason="no assertions defined"))
                return

            # First process overrides
            override_results = self.run_app_assertions(app, None,
                                                       overrides_only=True)
            # Then the rest
            self.run_app_assertions(app, override_results)

    def opt_exists(self, app_name, opt):
        return opt in self.params.bundle_apps[app_name].get('options', [])

    def run(self, context, allow_missing=False, ignore_fails=False):
        assertion = ASSERTIONS[context.method](context.settings)
        assertion.conf.bundle_apps = self.params.bundle_apps
        application = self.params.bundle_apps[context.application]

        assertion_scope = context.settings.get('scope', 'config')
        if assertion_scope == "application":
            result = assertion(context.opt, application)
            self.add_result(context.application, result)
            return result.passed

        supersedes = context.settings.get('supersedes', False)
        if (not allow_missing and
                not self.opt_exists(context.application, context.opt) and
                not supersedes):
            result = CheckResult(CheckResult.FAIL, opt=context.opt,
                                 reason="not found")
            self.add_result(context.application, result)
            return result.passed

        assertion_source = context.settings.get('source', 'local')
        if assertion_source == "local":
            assertion.conf.value = context.settings.get('value')
        elif assertion_source == "master":  # config/master.yaml
            if not self.params.fce_config:
                reason = "fce config not available - skipping"
                result = CheckResult(CheckResult.WARN, opt=context.opt,
                                     reason=reason)
                self.add_result(context.application, result)
                return result.passed

            # assertion["value"] must be python re compatible matching one
            # substring.
            result = assertion(context.opt, application)
            self.add_result(context.application, result)
            return result.passed
        elif assertion_source == "bucketsconfig":  # bucketsconfig.yaml
            if not self.params.fce_config:
                reason = "fce config not available - skipping"
                result = CheckResult(CheckResult.WARN, opt=context.opt,
                                     reason=reason)
                self.add_result(context.application, result)
                return result.passed

            assertion.conf.value = os.path.join(self.params.fce_config,
                                                "bucketsconfig.yaml")
        elif assertion_source == "bundle":
            # value is ignored, ensure that settings is non-null
            # only supported by isset() currently
            assertion.conf.value = None
        else:
            raise BundleCheckerError("Unknown assertion data source "
                                     f"'{assertion_source}'")

        result = assertion(context.opt, application)
        if result.passed or not ignore_fails:
            self.add_result(context.application, result)

        return result.passed

    def get_applications(self):
        self.applications = []
        for app in self.params.bundle_apps:
            regex_str = self.params.charm_regex
            charm = self.params.bundle_apps[app].get('charm')
            r = re.compile(CHARM_REGEX_TEMPLATE.format(
                regex_str, regex_str, regex_str)).match(charm)
            if r:
                self.charm_name = r[0]
                self.applications.append(app)

    def has_charm_matches(self):
        self.get_applications()
        return len(self.applications) > 0


def finish(checks_run):
    OUT.print("\nResults:")
    main_summary = {s: 0 for rc, s in CheckResult.RC_MAP.items()}
    for check in checks_run:
        check_summary = check.get_results_summary()
        for cat in check_summary:
            if main_summary.get(cat):
                main_summary[cat] += check_summary[cat]
            else:
                main_summary[cat] = check_summary[cat]

        check.show_results()

    # Show summary
    OUT.print("\nSummary:", stdout=True)
    for cat in main_summary:
        OUT.print(f" {cat}: {main_summary[cat]}", stdout=True)

    print("\nINFO: see --help for more options")
    print(f"Results saved in {OUT.logfile}")


def run_checks(checks, args, bundle_apps):
    """
    Execute all assertions.

    NOTE: a default assert_channel check is added for all charms if not
          provided in the yaml.
    """
    checks_run = []
    for label, assertions in checks.items():
        section = checks[label]
        assertions = section.get('assertions') or {}

        # Ensure we check charm_channel for all charms
        key = 'charm_channel'
        if (key not in assertions or
                assertions[key].get(AssertionAssertChannel.NAME,
                {}).get('scope') != 'application'):
            assertions[key] = {AssertionAssertChannel.NAME: {
                                        'scope': 'application'}}

        checker = UABundleChecker(UABundleCheckerParams(bundle_apps,
                                                        section['charm'],
                                                        assertions,
                                                        args.fce_config,
                                                        args.errors_only))
        if not args.errors_only and not checker.has_charm_matches():
            OUT.print("INFO: no match found for "
                      f"{checker.params.charm_regex} - skipping")

        checker.run_assertions()
        checks_run.append(checker)

    return checks_run


class ChecksManager:
    """
    Manage checks source. The user provides the type of bundle we are checking
    and that type maps to a checks yaml filename.

    A checks yaml can contain different groups of checks. By default the first
    group is used. To select a specific group, the name can be appended to the
    type name e.g. <type>:<group>.
    """

    def __init__(self, checks_type):
        script_root = os.path.dirname(__file__)
        self.group = None
        self.path = os.path.join(script_root, f'checks/{checks_type}.yaml')
        if not os.path.exists(self.path):
            self.checks_type, _, self.group = checks_type.partition(':')
            self.path = os.path.join(script_root,
                                     f'checks/{self.checks_type}.yaml')
        else:
            self.checks_type = checks_type

    @property
    def hash(self):
        checks_sha = hashlib.sha1()
        with open(self.path, 'rb') as fd:
            checks_sha.update(fd.read())

        return checks_sha

    @property
    def checks(self):
        """
        If 'checks' is the root key return everything beneath otherwise look
        for a matching group. If no group name is provided use the first one
        found.
        """
        with open(self.path, encoding='utf-8') as fd:
            check_defs = yaml.safe_load(fd.read())

        for group, checks in check_defs.items():
            if group == 'checks':
                return checks

            if self.group is None or self.group == group:
                return checks['checks']

        raise BundleCheckerError("no checks group found with name "
                                 f"'{self.group}' in {self.path}")


def setup(args):
    if args.schema:
        LocalAssertionHelpers({}).show_schema()
        sys.exit(0)

    bundle = None
    if args.bundle:
        bundle = args.bundle

    if args.fce_config:
        if not args.bundle:
            bundle = os.path.join(args.fce_config, "bundle.yaml")
        elif not os.path.exists(args.bundle):
            bundle = os.path.join(args.fce_config, args.bundle)
    elif bundle and not os.path.exists(args.bundle):
        raise BundleCheckerError("ERROR: --bundle must be a path")

    if not bundle:
        print("ERROR: one of --bundle or --fce-config is required")
        sys.exit(1)

    checks_mgr = ChecksManager(args.type)

    bundle_sha = hashlib.sha1()
    with open(bundle, 'rb') as fd:
        bundle_sha.update(fd.read())

    OutputManager(f"ua-bundle-checks.{checks_mgr.checks_type}.log",
                  not args.quiet).setup()
    OUT.print(HEADER_TEMPLATE.format(datetime.datetime.now(), args.type,
                                     bundle, bundle_sha.hexdigest(),
                                     checks_mgr.hash.hexdigest()),
              stdout=True)

    try:
        with open(bundle, encoding='utf-8') as fd:
            bundle_blob = fd.read()
    except OSError as e:
        OUT.print(f"ERROR: Error opening/reading bundle file: {e}")
        sys.exit(1)

    try:
        bundle_yaml = yaml.safe_load(bundle_blob)
    except ValueError as e:
        OUT.print(f"ERROR: Error parsing the bundle file: {e}")
        OUT.print("Please check the above errors and run again.")
        sys.exit(1)

    try:
        _bundle_apps = bundle_yaml['applications']
    except KeyError:
        # legacy juju fallback
        _bundle_apps = bundle_yaml['services']

    finish(run_checks(checks_mgr.checks, args, _bundle_apps))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--type', '-t', type=str,
                        default='openstack',
                        required=False,
                        help=("Type of bundle (openstack, kubernetes etc). "
                             "This name maps to a checks file under the "
                             "checks directory. If the checks are split into "
                             "more than one group, a group can be choses by "
                             "adding a :<group> to the end of the type."))
    parser.add_argument('--fce-config', type=str,
                        required=False, help="Path to FCE config.")
    parser.add_argument('--bundle', '-b', type=str,
                        required=False, help="Path to alternate bundle. "
                        "Default is to use $FCE_CONFIG/bundle.yaml")
    parser.add_argument('--errors-only', action='store_true', default=False,
                        help="Exclude [PASS] info.")
    parser.add_argument('--quiet', '-q', action='store_true', default=False)
    parser.add_argument('--schema', action='store_true', default=False)
    setup(parser.parse_args())
