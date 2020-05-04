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
 * bundle_sha1sum={}
 * assertions={}
"""
HEADER_TEMPLATE += "=" * 80


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

    RC_MAP = {0: 'PASS',
              1: 'WARN',
              2: 'FAIL'}

    def __init__(self, rc, opt=None, info=None, reason=None):
        self.rc = rc
        self.opt = opt
        self.reason = reason
        self.info = info
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
    def rc_str(self, formatted=False):
        fmt_map = {0: self._grn,
                   1: self._ylw,
                   2: self._red}
        if not formatted:
            return self.RC_MAP[self.rc]
        else:
            return fmt_map[self.rc](self.RC_MAP[self.rc])

    @property
    def rc_str_fmt(self):
        map = {0: self._grn('PASS'),
               1: self._ylw('WARN'),
               2: self._red('FAIL')}
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


class UABundleChecker(object):

    def __init__(self, app, bundle_apps, charm_regex, assertions, fce_config,
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

    def show_results(self, ignore_pass=False):
        if not self.results:
            return

        for app in self.results:
            results = self.results[app]
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

    def run_assertions(self):
        if not self.assertions:
            self.add_result(CheckResult(2, reason="no assertions defined"))
            return

        if not self.has_charm_matches():
            return

        for app in self.applications:
            self.app_name = app
            defaults_key = "allow_default"
            for opt in self.assertions:
                if defaults_key in self.assertions[opt]:
                    # if opt is not set in bundle and we have allowed charm default
                    # then we log a PASS and continue to the next opt in the
                    # assertions list.
                    if not self.opt_exists(opt):
                        reason = "using charm default"
                        self.add_result(CheckResult(0, opt=opt, reason=reason))
                        continue
                    else:
                        # otherwise we continue with asserting the value set.
                        del self.assertions[opt][defaults_key]

                for method in self.assertions[opt]:
                    self.run(opt, method, self.assertions[opt][method])

    def opt_exists(self, opt):
        return opt in self.bundle_apps[self.app_name].get('options', [])

    def run(self, opt, method, assertion):

        if assertion['type'] == "application":
            getattr(self, method)()
            return

        if not self.opt_exists(opt):
            self.add_result(CheckResult(2, opt=opt, reason="not found"))
            return

        if assertion["source"] == "local":
            value = assertion["value"]
        elif assertion["source"] == "master":  # config/master.yaml
            if not self.fce_config:
                reason = "fce config not available - skipping"
                self.add_result(CheckResult(1, opt=opt, reason=reason))
                return

            master = os.path.join(self.fce_config, "master.yaml")
            # this must be python re compatible with 1 substring match
            regexp = assertion["regexp"]
            value = None
            with open(master) as fd:
                for line in fd.readlines():
                    r = re.match(re.compile(regexp), line)
                    if r:
                        value = r[1]
            if not value:
                reason = ("no match found in {} with: {}".
                          format(master, assertion['regexp']))
                self.add_result(CheckResult(2, opt=opt, reason=reason))
                return
        elif assertion["source"] == "bundle":
            # value is ignored, ensure that settings is non-null
            # only supported by isset() currently
            value = None
        else:
            raise Exception("Unknown assertion data source")

        getattr(self, method)(opt, value)

    def atoi(self, val):
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

    def assert_ha(self):
        min_units = 3
        num_units = self.bundle_apps[self.app_name].get('num_units', -1)
        ret = CheckResult(0, opt="HA (>={})".format(min_units))
        if num_units < min_units:
            ret.reason = ("not enough units (value={}, expected='>={}')".
                          format(num_units, min_units))
            ret.rc = 2

        self.add_result(ret)

    def gte(self, opt, value):
        current = self.bundle_apps[self.app_name].get('options', [])[opt]
        current = self.atoi(current)
        expected = self.atoi(value)
        ret = CheckResult(0, opt=opt, reason=("value={}".format(current)))
        if current < expected:
            ret.reason = "value={}, expected={}".format(current, expected)
            ret.rc = 2

        self.add_result(ret)

    def eq(self, opt, value):
        current = self.bundle_apps[self.app_name].get('options', [])[opt]
        current = self.atoi(current)
        expected = self.atoi(value)
        ret = CheckResult(0, opt=opt, reason=("value={}".format(current)))
        if current != expected:
            ret.reason = "value={}, expected={}".format(current, expected)
            ret.rc = 2

        self.add_result(ret)

    def isset(self, opt, value):
        current = self.bundle_apps[self.app_name].get('options', [])[opt]
        ret = CheckResult(0, opt=opt, reason="value={}".format(current))
        if not current:
            ret.reason = "no value set"
            ret.rc = 1

        self.add_result(ret)

    def get_applications(self):
        self.applications = []
        for app in self.bundle_apps:
            r = re.match(re.compile(self.charm_regex),
                         self.bundle_apps[app].get('charm'))
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
    args = parser.parse_args()

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

    checks_path = 'checks/{}.yaml'.format(args.type)
    bundle_sha = hashlib.sha1()
    bundle_sha.update(open(bundle, 'rb').read())

    logger = Logger("ua-bundle-checks.{}.log".format(args.type),
                    not args.quiet)
    logger.log(HEADER_TEMPLATE.format(datetime.datetime.now(), args.type,
                                      bundle, bundle_sha.hexdigest(),
                                      checks_path), stdout=True)

    bundle_apps = yaml.safe_load(open(bundle).read())['applications']
    check_defs = yaml.safe_load(open(checks_path).read())
    checks_run = []

    for label in check_defs['checks']:
        charm = check_defs['checks'][label]['charm']
        assertions = check_defs['checks'][label].get('assertions')
        if not assertions:
            print("INFO: {} has no assertions defined".format(label))
            continue

        checker = UABundleChecker(label, bundle_apps, charm, assertions,
                                  args.fce_config, logger)
        matches = checker.has_charm_matches()
        if not matches:
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
    print("Results are logged in {}".format(logger.logfile))
