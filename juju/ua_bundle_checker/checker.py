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
CHARM_REGEX_TEMPLATE = (r'^(cs|ch|local):(~?.+/)?{}[-]?[0-9]*$|'
                        r'^[\/\.]*{}[-]?[0-9]*$|'
                        r'^(\.?|~)(/[^/ ]*)+/?{}[-]?[0-9]*$')
OST_CHARM_CHANNELS_GUIDE_URL = (
    "https://docs.openstack.org/charm-guide/latest/project/charm-delivery.html"
)


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
    SKIPPED = 3
    RC_MAP = {PASS: 'PASS',
              WARN: 'WARN',
              FAIL: 'FAIL',
              SKIPPED: 'SKIPPED'}

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
    def skipped(self):
        return self.rc == self.SKIPPED

    @property
    def rc_str(self):
        return self.RC_MAP[self.rc]

    @property
    def rc_str_fmt(self):
        _map = {self.PASS: self._grn('PASS'),
               self.WARN: self._ylw('WARN'),
               self.SKIPPED: self._ylw('SKIPPED'),
               self.FAIL: self._red('FAIL')}
        return _map[self.rc]

    def unformatted(self):
        self.formatted = False
        return str(self)

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
        if not isinstance(val, str):
            return val

        if not isinstance(val[-1], str):
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

        return application.get('scale', 1)


class LocalAssertionHelpers(AssertionBase):

    def __init__(self, bundle_apps):
        super().__init__()
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
                       self.assert_channel.__name__:
                       {'description':
                        '"Ensure application using valid charmhub channel"',
                        'scope': 'application',
                        'source': 'bundle'},
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

    def allow_default(self, application, opt,
                      value, warn_on_fail=False,  # pylint: disable=W0613
                      description=None):
        ret = CheckResult(opt=opt)
        if opt not in application.get('options', []):
            ret.reason = "using charm config default"
            if description:
                ret.reason = "{}: {}".format(ret.reason, description)

            return ret

        ret.rc = CheckResult.FAIL
        return ret

    def skip_if_charm_exists(self, application, opt, value, warn_on_fail=False,  # noqa pylint: disable=W0613
                             description=None):
        ret = CheckResult()
        regex_str = value
        for app in self.bundle_apps:
            charm = self.bundle_apps[app].get('charm')
            r = re.compile(CHARM_REGEX_TEMPLATE.format(
                regex_str, regex_str, regex_str)).match(charm)
            if r:
                ret.reason = ("charm {} found in bundle - skipping check".
                              format(charm))
                if description:
                    ret.reason = "{}: {}".format(ret.reason, description)

                return ret

        ret.rc = CheckResult.FAIL
        return ret

    @staticmethod
    def assertion_opts_common():
        return {'scope': "[config|application]",
                'source': "[local|bundle|master]",
                'value': "<value>  # if 'source: master' this must "
                         "be regex with single substring match",
                'warn-on-fail': 'bool',
                'skip': 'bool'}

    def assert_ha(self, application, _, warn_on_fail=False,
                  description=None):
        _min = 3
        num_units = self.get_units(application)
        ret = CheckResult(opt="HA (>={})".format(_min))
        if num_units < _min:
            ret.reason = ("not enough units (value={}, expected='>={}')".
                          format(num_units, _min))
            if description:
                ret.reason = "{}: {}".format(ret.reason, description)

            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret

    def assert_channel(self, application, value, warn_on_fail=False,
                       description=None):
        channel = application.get('channel')
        ret = CheckResult(opt="charmhub channel ({})".format(channel))
        if not channel:
            if application['charm'].startswith('local:'):
                # no channel expected if its a local charm
                return ret

            ret.reason = ("channel is unset - see {}".
                          format(OST_CHARM_CHANNELS_GUIDE_URL))
            if description:
                ret.reason = "{}: {}".format(ret.reason, description)

            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

            return ret

        if value is None:
            _ret = re.match(r'.*latest/\S+', channel)
            if not _ret:
                return ret

            channel = _ret.group(0)
        else:
            if value == channel:
                return ret

        ret.reason = ("channel is set to {} which is "
                      "not supported - see {}".
                      format(channel, OST_CHARM_CHANNELS_GUIDE_URL))
        if description:
            ret.reason = "{}: {}".format(ret.reason, description)

        if warn_on_fail:
            ret.rc = CheckResult.WARN
        else:
            ret.rc = CheckResult.FAIL

        return ret

    def gte(self, application, opt, value, warn_on_fail=False,
            description=None):
        current = application.get('options', [])[opt]
        current = self.atoi(current)
        expected = self.atoi(value)
        ret = CheckResult(opt=opt, reason="value={}".format(current))
        if current < expected:
            ret.reason = "value={}, expected={}".format(current, expected)
            if description:
                ret.reason = "{}: {}".format(ret.reason, description)

            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret

    def neq(self, application, opt, value, warn_on_fail=False,
            description=None):
        current = application.get('options', [])[opt]
        current = self.atoi(current)
        expected = self.atoi(value)
        ret = CheckResult(opt=opt, reason="value={}".format(current))
        if current == expected:
            ret.reason = "value '{}' is not valid".format(current)
            if description:
                ret.reason = "{}: {}".format(ret.reason, description)

            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret

    def eq(self, application, opt, value, warn_on_fail=False,
           description=None):
        current = application.get('options', [])[opt]
        current = self.atoi(current)
        expected = self.atoi(value)
        ret = CheckResult(opt=opt, reason="value={}".format(current))
        if current != expected:
            ret.reason = "value={}, expected={}".format(current, expected)
            if description:
                ret.reason = "{}: {}".format(ret.reason, description)

            if warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret

    def isset(self, app, opt, value, warn_on_fail=False,  # noqa pylint: disable=W0613
              description=None):
        current = app.get('options', [])[opt]
        ret = CheckResult(opt=opt, reason="value={}".format(current))
        if not current:
            ret.reason = "no value set"
            if description:
                ret.reason = "{}: {}".format(ret.reason, description)

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

    def exclusive_backing_dev(self, app, opt, value, warn_on_fail=False,
                              description=None):
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
                    if description:
                        ret.reason = "{}: {}".format(ret.reason, description)

                    if warn_on_fail:
                        ret.rc = CheckResult.WARN
                    else:
                        ret.rc = CheckResult.FAIL

        return ret


class MasterAssertionHelpers(LocalAssertionHelpers):

    def __init__(self, master_path):
        super().__init__(bundle_apps=None)
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
        ret.reason = "check disabled - please check this one manually"


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

        for app, results in self.results.items():
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
        for results in self.results.values():
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
        for method, settings in schema.items():
            if settings.get('override_method'):
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
            overrides = self.get_overrides()

            for opt in self.assertions:
                if any(overrides.get(opt, {}).values()):
                    continue

                for method in self.assertions[opt]:
                    if method in overrides.get(opt, {}):
                        continue

                    desc = self.assertions[opt][method].get('description')
                    if not self.run(opt, method, description=desc):
                        # stop at the first failure
                        break

    def opt_exists(self, opt):
        return opt in self.bundle_apps[self.app_name].get('options', [])

    def run(self, opt, method, description=None, allow_missing=False,  # noqa, pylint: disable=R0911
            ignore_fails=False):
        assertion = self.assertions[opt][method]
        application = self.bundle_apps[self.app_name]
        warn_on_fail = assertion.get('warn-on-fail', False)

        skip = assertion.get('skip', False)
        if skip:
            return CheckResult().SKIPPED

        assertion_scope = assertion.get('scope', 'config')
        if assertion_scope == "application":
            result = getattr(self.local_assertion_helpers,
                             method)(application, assertion.get('value'),
                                     warn_on_fail=warn_on_fail)
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
                                 description=description,
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


def setup(args):
    if args.schema:
        asshelper = LocalAssertionHelpers(None)
        print("# Assertion schema generated using 'ua-bundle-check.py "
              "--schema'")
        print("checks:")
        print("  <label>:")
        print("    charm: <regex>")
        print("      <charm-option>:")
        print("      assertions:")
        for key, _value in asshelper.schema.items():
            print("        {}:".format(key))
            print("          description: {}".format(_value['description']))
            opts = asshelper.assertion_opts_common()
            for _opt, _opt_val in opts.items():
                if _opt in _value:
                    if _opt_val:
                        print("          {}: {}".format(_opt, _opt_val))

                    continue

                print("          {}: {}".format(_opt, _opt_val))
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
    with open(checks_path, 'rb') as fd:
        checks_sha.update(fd.read())

    bundle_sha = hashlib.sha1()
    with open(bundle, 'rb') as fd:
        bundle_sha.update(fd.read())

    _logger = Logger("ua-bundle-checks.{}.log".format(args.type),
                    not args.quiet)
    _logger.log(HEADER_TEMPLATE.format(datetime.datetime.now(), args.type,
                                      bundle, bundle_sha.hexdigest(),
                                      checks_sha.hexdigest()), stdout=True)

    try:
        with open(bundle) as fd:
            bundle_blob = fd.read()
    except Exception as e:
        _logger.log("ERROR: Error opening/reading bundle file: {}".format(e))
        sys.exit(1)

    try:
        bundle_yaml = yaml.safe_load(bundle_blob)
    except Exception as e:
        _logger.log("ERROR: Error parsing the bundle file: {}".format(e))
        _logger.log("Please check the above errors and run again.")
        sys.exit(1)

    try:
        _bundle_apps = bundle_yaml['applications']
    except KeyError:
        _bundle_apps = bundle_yaml['services']

    with open(checks_path) as fd:
        check_defs = yaml.safe_load(fd.read())

    checks_run = []

    for _label in check_defs['checks']:
        _charm = check_defs['checks'][_label]['charm']
        _assertions = check_defs['checks'][_label].get('assertions')
        if not _assertions:
            if not args.errors_only:
                _logger.log("INFO: {} has no assertions defined".
                            format(_label))
            continue

        # Always add channel check if not explicitly set in checks.
        chan_assert = _assertions.get('channel')
        if (not chan_assert or
                chan_assert.get('assert_channel', {}).get('scope') !=
                'application'):
            _assertions['charmhub_channel'] = {'assert_channel': {
                                               'scope': 'application'}}

        checker = UABundleChecker(_bundle_apps, _charm, _assertions,
                                  args.fce_config, _logger)
        matches = checker.has_charm_matches()
        if not args.errors_only and not matches:
            _logger.log("INFO: no match found for {} - skipping"
                       .format(checker.charm_regex))
        checker.run_assertions()
        checks_run.append(checker)

    _logger.log("\nResults:")
    main_summary = {s: 0 for rc, s in CheckResult.RC_MAP.items()}
    for check in checks_run:
        check_summary = check.get_results_summary()
        for cat in check_summary:
            if main_summary.get(cat):
                main_summary[cat] += check_summary[cat]
            else:
                main_summary[cat] = check_summary[cat]

        check.show_results(ignore_pass=args.errors_only)

    # Show summary
    _logger.log("\nSummary:", stdout=True)
    for cat in main_summary:
        _logger.log(" {}: {}".format(cat, main_summary[cat]), stdout=True)

    print("\nINFO: see --help for more options")
    print("Results saved in {}".format(_logger.logfile))


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
    setup(parser.parse_args())
