#!/usr/bin/env python3
# Copyright 2020 Canonical Ltd
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

import argparse
import datetime
import hashlib
import re
import yaml

CSI = "\033["
RES = "{}0m".format(CSI)

HEADER_TEMPLATE = "=" * 80
HEADER_TEMPLATE += """
UA Juju bundle config verification
 * {}
 * type={}
 * bundle={}
 * bundle_sha1={}
 * assertions_sha1={}
"""
HEADER_TEMPLATE += "=" * 80
# e.g. cs:barbican-vault-123 or ./barbican-vault
CHARM_REGEX_TEMPLATE = "^cs:(~.+/)?{}[-]?[0-9]*$|" \
                       "^[\/\.]*{}$|^(\.?|~)(/[^/ ]*)+/?{}$"


class Logger(object):

    def __init__(self, logfile, verbose=False):
        self.logfile = logfile
        self.verbose = verbose

        if os.path.exists(self.logfile):
            os.unlink(self.logfile)

    def log(self, entry, stdout=False):
        if self.verbose or stdout:
            print(entry)

        with open(self.logfile, 'a') as fd:
            if hasattr(entry, 'unformatted'):
                entry = entry.unformatted()

            fd.write("{}\n".format(entry))


class CheckResult(object):

    PASS = 0
    WARN = 1
    FAIL = 2
    RC_MAP = {PASS: 'PASS',
              WARN: 'WARN',
              FAIL: 'FAIL'}

    def __init__(self, rc=PASS, opt=None, reason=None):
        self.rc = rc
        self.opt = opt
        self.reason = reason
        self.formatted = True

    @staticmethod
    def _red(s):
        return "{}31m{}{}".format(CSI, s, RES)

    @staticmethod
    def _grn(s):
        return "{}32m{}{}".format(CSI, s, RES)

    @staticmethod
    def _ylw(s):
        return "{}33m{}{}".format(CSI, s, RES)

    @property
    def passed(self):
        return self.rc == self.PASS

    @property
    def rc_str(self, formatted=False):
        fmt_map = {self.PASS: self._grn,
                   self.WARN: self._ylw,
                   self.FAIL: self._red}
        if not formatted:
            return self.RC_MAP[self.rc]
        else:
            return fmt_map[self.rc](self.RC_MAP[self.rc])

    @property
    def rc_str_fmt(self):
        map = {self.PASS: self._grn('PASS'),
               self.WARN: self._ylw('WARN'),
               self.FAIL: self._red('FAIL')}
        return map[self.rc]

    def unformatted(self):
        self.formatted = False
        return self.__str__()

    def __str__(self):
        if self.formatted:
            msg = "[{}]".format(self.rc_str_fmt)
        else:
            msg = "[{}]".format(self.rc_str)

        if self.opt:
            msg += " {}".format(self.opt)
        if self.reason:
            msg += " ({})".format(self.reason)

        return msg


class AssertionBase(object):

    @staticmethod
    def atoi(val):
        if type(val) != str:
            return val

        if type(val[-1]) != str:
            return val

        try:
            _int = int(val[0:-1])
        except Exception:
            return val

        quotient = 1024
        if val[-1].lower() == val[-1]:
            quotient = 1000

        conv = {"g": quotient ** 3,
                "m": quotient ** 2,
                "k": quotient}

        return _int * conv[val[-1].lower()]

    def get_units(self, application):
        if 'num_units' in application:
            return application['num_units']
        else:
            return application.get('scale')

        return -1


class LocalAssertionHelpers(AssertionBase):

    def __init__(self, bundle_apps):
        super(LocalAssertionHelpers, self).__init__()
        self.bundle_apps = bundle_apps
        self.schema = {'allow_default':
                       {'description':
                        '"Allow charm default if config not provided."',
                        'scope': 'config',
                        'source': 'bundle',
                        'value': None,
                        'override_method': True},
                       self.skip_if_charm_exists.__name__:
                       {'description':
                        '"Skip check if charm exists"',
                        'source': 'bundle',
                        'value': None,
                        'override_method': True},
                       self.assert_ha.__name__:
                       {'description':
                        '"Ensure application has minimum number of units"',
                        'scope': 'application',
                        'source': 'bundle',
                        'value': None},
                       self.gte.__name__:
                       {'description':
                        '"Ensure option is gte to value"'},
                       self.eq.__name__:
                       {'description':
                        '"Ensure option equal to value"'},
                       self.neq.__name__:
                       {'description':
                        '"Ensure option not equal to value"'},
                       self.isset.__name__:
                       {'description':
                        '"Ensure option has a provided value"',
                        'source': 'bundle',
                        'value': None}}

    def allow_default(self, application, opt, value, warn_on_fail=False):
        ret = CheckResult(opt=opt)
        if opt not in application.get('options', []):
            ret.reason = "using charm config default"
            return ret

        ret.rc = CheckResult.FAIL
        return ret

    def skip_if_charm_exists(self, application, opt, value,
                             warn_on_fail=False):
        ret = CheckResult()
        regex_str = value
        for app in self.bundle_apps:
            charm = self.bundle_apps[app].get('charm')
            r = re.compile(CHARM_REGEX_TEMPLATE.format(
                regex_str, regex_str, regex_str)).match(charm)
            if r:
                ret.reason = ("charm {} found in bundle - skipping check".
                              format(charm))
                return ret

        ret.rc = CheckResult.FAIL
        return ret

    @staticmethod
    def assertion_opts_common():
        return {'scope': "[config|application]",
                'source': "[local|bundle|master]",
                'value': "<value>  # if 'source: master' this must "
                         "be regex with single substring match",
                'warn-on-fail': 'bool'}

    def assert_ha(self, application, warn_on_fail=False):
        min = 3
        num_units = self.get_units(application)
        ret = CheckResult(opt="HA (>={})".format(min))
        if num_units < min:
            ret.reason = ("not enough units (value={}, expected='>={}')".
                          format(num_units, min))
            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret

    def gte(self, application, opt, value, warn_on_fail=False):
        current = application.get('options', [])[opt]
        current = self.atoi(current)
        expected = self.atoi(value)
        ret = CheckResult(opt=opt, reason=("value={}".format(current)))
        if current < expected:
            ret.reason = "value={}, expected={}".format(current, expected)
            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret

    def neq(self, application, opt, value, warn_on_fail=False):
        current = application.get('options', [])[opt]
        current = self.atoi(current)
        expected = self.atoi(value)
        ret = CheckResult(opt=opt, reason=("value={}".format(current)))
        if current == expected:
            ret.reason = "value={}, expected={}".format(current, expected)
            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret

    def eq(self, application, opt, value, warn_on_fail=False):
        current = application.get('options', [])[opt]
        current = self.atoi(current)
        expected = self.atoi(value)
        ret = CheckResult(opt=opt, reason=("value={}".format(current)))
        if current != expected:
            ret.reason = "value={}, expected={}".format(current, expected)
            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret

    def isset(self, app, opt, value, warn_on_fail=False):
        current = app.get('options', [])[opt]
        ret = CheckResult(opt=opt, reason="value={}".format(current))
        if not current:
            ret.reason = "no value set"
            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret

    def _find_disklabel_users(self, disks, label):
        devs = []
        for disk in disks:
            if disk['type'] == "bcache":
                backing_dev = disk['backing_device']
                disklabel = re.compile("([a-z0-9]+)-.+").match(backing_dev)
                if disklabel and disklabel[1] == label:
                    devs.append(disk.get('name', "unknown"))

        return devs

    def exclusive_backing_dev(self, app, opt, value, warn_on_fail=False):
        current = app.get('options', [])[opt]
        ret = CheckResult(opt=opt, reason="value={}".format(current))

        with open(value) as fd:
            y = yaml.safe_load(fd)
            disks = y.get('configs',
                          {}).get('hyperconverged',
                                  {}).get('disks', {})

            diskprefix = None
            for disk in disks:
                if disk.get('name') == os.path.basename(current):
                    if disk['type'] == "bcache":
                        backing_dev = disk['backing_device']
                        diskprefix = (re.compile("([a-z0-9]+)-.+")
                                      .match(backing_dev))
                        break

            if diskprefix:
                devs = self._find_disklabel_users(disks, diskprefix[1])
                if len(devs) > 1:
                    ret.reason = ("bcaches sharing same backing disk: {}"
                                  .format(devs))
                    if warn_on_fail:
                        ret.rc = CheckResult.WARN
                    else:
                        ret.rc = CheckResult.FAIL

        return ret


class MasterAssertionHelpers(LocalAssertionHelpers):

    def __init__(self, master_path):
        super(MasterAssertionHelpers, self).__init__(bundle_apps=None)
        self.master_path = master_path

    def eq(self, application, opt, value, warn_on_fail=False):
        # FIXME(hopem): this check is not currently viable since it requires
        # checking many different sources and cross-referencing them to ensure
        # they are correct e.g. kernel_opts can be provided is maas tags or
        # boot defaults or the sysconfig charm AND they can be specified in
        # maas with a meaning that applies to multiple charms. So for now I'm
        # disabling this and will consider either removing altogether or
        # finding a way to make it meaningfil.
        ret = CheckResult(CheckResult.WARN, opt=opt)
        ret.reason = ("check disabled - please check this one manually")
        return ret
        master_value = None

        with open(self.master_path) as fd:
            for line in fd.readlines():
                r = re.compile(value).match(line)
                if r:
                    master_value = r[1]
                    break

        if master_value:
            return super(MasterAssertionHelpers, self).eq(
                         application, opt, master_value, warn_on_fail)
        else:
            ret = CheckResult(opt=opt)
            ret.reason = ("no match found in {} with: {}".
                          format(self.master_path, value))
            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

            return ret


class UABundleChecker(object):

    def __init__(self, bundle_apps, charm_regex, assertions, fce_config,
                 logger):
        self.applications = []
        self.app_name = None
        self.bundle_apps = bundle_apps
        self.charm_regex = charm_regex
        self.assertions = assertions
        self.fce_config = fce_config
        self.logger = logger
        self.charm_name = None
        self.results = {}
        self.local_assertion_helpers = LocalAssertionHelpers(bundle_apps)
        if self.fce_config:
            master_path = os.path.join(self.fce_config, "master.yaml")
            self.master_assertion_helpers = MasterAssertionHelpers(master_path)

    def show_results(self, ignore_pass=False):
        if not self.results:
            return

        for app in self.results:
            results = self.results[app]
            if ignore_pass and set(results.keys()) == set(["PASS"]):
                continue

            self.logger.log("=> application '{}'".format(app))
            for category in results:
                if ignore_pass and category == "PASS":
                    continue

                for result in results[category]:
                    self.logger.log(result)

    def get_results_summary(self):
        summary = {}
        for app in self.results:
            results = self.results[app]
            for category in results:
                if category in summary:
                    summary[category] += len(results[category])
                else:
                    summary[category] = len(results[category])

        return summary

    def add_result(self, result):
        if self.app_name not in self.results:
            self.results[self.app_name] = {}

        results = self.results[self.app_name]
        if result.rc_str in results:
            results[result.rc_str].append(result)
        else:
            results[result.rc_str] = [result]

    def get_overrides(self):
        """
        If the application has assertion methods that are overrides i.e. if
        any one passes it superscedes all others, process those first and
        mark them so that they don't get executed again.
        """
        _methods = []
        schema = LocalAssertionHelpers(None).schema
        for method in schema:
            if schema[method].get('override_method'):
                _methods.append(method)

        overrides = {}
        for opt in self.assertions:
            for method in _methods:
                if method in self.assertions[opt]:
                    if opt in overrides:
                        overrides[opt][method] = False
                    else:
                        overrides[opt] = {method: False}

                    passed = self.run(opt, method, allow_missing=True,
                                      ignore_fails=True)
                    if passed:
                        overrides[opt][method] = True

        return overrides

    def run_assertions(self):
        if not self.assertions:
            self.add_result(CheckResult(CheckResult.FAIL,
                                        reason="no assertions defined"))
            return

        if not self.has_charm_matches():
            return

        for app in self.applications:
            self.app_name = app
            defaults_key = "allow_default"
            overrides = self.get_overrides()

            for opt in self.assertions:
                if any(overrides.get(opt, {}).values()):
                    continue

                for method in self.assertions[opt]:
                    if method in overrides.get(opt, {}):
                        continue

                    if not self.run(opt, method):
                        # stop at the first failure
                        break

    def opt_exists(self, opt):
        return opt in self.bundle_apps[self.app_name].get('options', [])

    def run(self, opt, method, allow_missing=False, ignore_fails=False):
        assertion = self.assertions[opt][method]
        application = self.bundle_apps[self.app_name]
        warn_on_fail = assertion.get('warn-on-fail', False)

        assertion_scope = assertion.get('scope', 'config')
        if assertion_scope == "application":
            result = getattr(self.local_assertion_helpers,
                             method)(application, warn_on_fail=warn_on_fail)
            self.add_result(result)
            return result.passed

        if not allow_missing and not self.opt_exists(opt):
            result = CheckResult(CheckResult.FAIL, opt=opt,
                                 reason="not found")
            self.add_result(result)
            return result.passed

        assertion_source = assertion.get('source', 'local')
        if assertion_source == "local":
            value = assertion.get('value')
        elif assertion_source == "master":  # config/master.yaml
            if not self.fce_config:
                reason = "fce config not available - skipping"
                result = CheckResult(CheckResult.WARN, opt=opt, reason=reason)
                self.add_result(result)
                return result.passed

            # assertion["value"] must be python re compatible macthing one
            # substring.
            result = getattr(self.master_assertion_helpers,
                             method)(application, opt, assertion["value"],
                                     warn_on_fail=warn_on_fail)
            self.add_result(result)
            return result.passed
        elif assertion_source == "bucketsconfig":  # bucketsconfig.yaml
            if not self.fce_config:
                reason = "fce config not available - skipping"
                result = CheckResult(CheckResult.WARN, opt=opt, reason=reason)
                self.add_result(result)
                return result.passed

            value = os.path.join(self.fce_config, "bucketsconfig.yaml")
        elif assertion_source == "bundle":
            # value is ignored, ensure that settings is non-null
            # only supported by isset() currently
            value = None
        else:
            raise Exception("Unknown assertion data source '{}'".format(
                assertion_source))

        result = getattr(self.local_assertion_helpers,
                         method)(application, opt, value,
                                 warn_on_fail=warn_on_fail)

        if result.passed or not ignore_fails:
            self.add_result(result)

        return result.passed

    def get_applications(self):
        self.applications = []
        for app in self.bundle_apps:
            regex_str = self.charm_regex
            charm = self.bundle_apps[app].get('charm')
            r = re.compile(CHARM_REGEX_TEMPLATE.format(
                regex_str, regex_str, regex_str)).match(charm)
            if r:
                self.charm_name = r[0]
                self.applications.append(app)

    def has_charm_matches(self):
        self.get_applications()
        return len(self.applications) > 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--type', '-t', type=str,
                        default='openstack',
                        required=False,
                        help="Type of bundle (openstack, kubernetes etc)")
    parser.add_argument('--fce-config', type=str,
                        required=False, help="Path to FCE config.")
    parser.add_argument('--bundle', '-b', type=str,
                        required=False, help="Path to alternate bundle. "
                        "Default is to use $FCE_CONFIG/bundle.yaml")
    parser.add_argument('--errors-only', action='store_true', default=False,
                        help="Exclude [PASS] info.")
    parser.add_argument('--quiet', '-q', action='store_true', default=False)
    parser.add_argument('--schema', action='store_true', default=False)
    args = parser.parse_args()

    if args.schema:
        asshelper = LocalAssertionHelpers(None)
        print("# Assertion schema generated using 'ua-bundle-check.py "
              "--schema'")
        print("checks:")
        print("  <label>:")
        print("    charm: <regex>")
        print("      <charm-option>:")
        print("      assertions:")
        for key, value in asshelper.schema.items():
            print("        {}:".format(key))
            print("          description: {}".format(value['description']))
            opts = asshelper.assertion_opts_common()
            for opt in opts:
                if opt in value:
                    if value[opt]:
                        print("          {}: {}".format(opt, value[opt]))
                    continue
                values = opts[opt]
                print("          {}: {}".format(opt, values))
        print("")
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
        raise Exception("ERROR: --bundle must be a path")

    if not bundle:
        print("ERROR: one of --bundle or --fce-config is required")
        sys.exit(1)

    script_root = os.path.dirname(__file__)
    checks_path = os.path.join(script_root, 'checks/{}.yaml'.format(args.type))
    checks_sha = hashlib.sha1()
    checks_sha.update(open(checks_path, 'rb').read())

    bundle_sha = hashlib.sha1()
    bundle_sha.update(open(bundle, 'rb').read())

    logger = Logger("ua-bundle-checks.{}.log".format(args.type),
                    not args.quiet)
    logger.log(HEADER_TEMPLATE.format(datetime.datetime.now(), args.type,
                                      bundle, bundle_sha.hexdigest(),
                                      checks_sha.hexdigest()), stdout=True)

    bundle_apps = yaml.safe_load(open(bundle).read())['applications']
    check_defs = yaml.safe_load(open(checks_path).read())
    checks_run = []

    for label in check_defs['checks']:
        charm = check_defs['checks'][label]['charm']
        assertions = check_defs['checks'][label].get('assertions')
        if not assertions:
            if not args.errors_only:
                logger.log("INFO: {} has no assertions defined".format(label))
            continue

        checker = UABundleChecker(bundle_apps, charm, assertions,
                                  args.fce_config, logger)
        matches = checker.has_charm_matches()
        if not args.errors_only and not matches:
            logger.log("INFO: no match found for {} - skipping"
                       .format(checker.charm_regex))
        checker.run_assertions()
        checks_run.append(checker)

    logger.log("\nResults:")
    summary = {s: 0 for rc, s in CheckResult.RC_MAP.items()}
    for check in checks_run:
        s = check.get_results_summary()
        for cat in s:
            if summary.get(cat):
                summary[cat] += s[cat]
            else:
                summary[cat] = s[cat]

        check.show_results(ignore_pass=args.errors_only)

    # Show summary
    logger.log("\nSummary:", stdout=True)
    for cat in summary:
        logger.log(" {}: {}".format(cat, summary[cat]), stdout=True)

    print("\nINFO: see --help for more options")
    print("Results saved in {}".format(logger.logfile))
