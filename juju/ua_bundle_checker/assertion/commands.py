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
import re

from functools import cached_property

import yaml

from ua_bundle_checker.assertion.opts import (
    AssertionOptsCommon,
    AssertHAAssertionOpts,
    IsSetAssertionOpts,
)

CSI = "\033["
RES = f"{CSI}0m"
# e.g. cs:barbican-vault-123 or ./barbican-vault
CHARM_REGEX_TEMPLATE = (r'^(cs|ch|local):(~?.+/)?{}[-]?[0-9]*$|'
                        r'^[\/\.]*{}[-]?[0-9]*$|'
                        r'^(\.?|~)(/[^/ ]*)+/?{}[-]?[0-9]*$')
OST_CHARM_CHANNELS_GUIDE_URL = (
    "https://docs.openstack.org/charm-guide/latest/project/charm-delivery.html"
)
SCHEMA_HEADER = """
# Assertion schema generated using 'ua-bundle-check.py --schema'
checks:
  <label>:
    charm: <regex>
    <charm-option> or "ha":
      assertions:
""".strip()
SCHEMA_ASSERTION_HEADER = """        {key}:
          purpose: {purpose}
          params:
""".rstrip()


ASSERTIONS = {}


def register(name):
    """
    Decorator to register an assertion helper.

    @param name: assertion method name
    """
    def _register(c):
        c.NAME = name
        ASSERTIONS[name] = c
        return c

    return _register


class CheckResult:
    """ Represents the result of an assertion check. """
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
        return f"{CSI}31m{s}{RES}"

    @staticmethod
    def _grn(s):
        return f"{CSI}32m{s}{RES}"

    @staticmethod
    def _ylw(s):
        return f"{CSI}33m{s}{RES}"

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
            msg = f"[{self.rc_str_fmt}]"
        else:
            msg = f"[{self.rc_str}]"

        if self.opt:
            msg += f" {self.opt}"
        if self.reason:
            msg += f" ({self.reason})"

        return msg


class AssertionBase:
    """ Base class for all assertion implementations. """
    NAME = None
    OPTS = None
    IS_OVERRIDE = False

    def __init__(self, settings):
        for name, value in settings.items():
            for opt in self.conf:
                if opt.name == name:
                    opt.value = value
                    break

    @cached_property
    def conf(self):
        return self.OPTS()  # pylint: disable=not-callable

    @staticmethod
    def atoi(val):
        if not isinstance(val, str):
            return val

        if not isinstance(val[-1], str):
            return val

        try:
            _int = int(val[0:-1])
        except ValueError:
            return val

        quotient = 1024
        if val[-1].lower() == val[-1]:
            quotient = 1000

        conv = {"g": quotient ** 3,
                "m": quotient ** 2,
                "k": quotient}

        return _int * conv[val[-1].lower()]

    @staticmethod
    def get_units(application):
        if 'num_units' in application:
            return application['num_units']

        return application.get('scale', 1)


@register('allow_default')
class AssertionAllowDefault(AssertionBase):
    """
    Return True if charm config option is not set thus permitting its default.
    """
    IS_OVERRIDE = True
    OPTS = AssertionOptsCommon

    def __call__(self, charm_config_opt, application):
        if self.conf.skip:
            return CheckResult(rc=CheckResult.SKIPPED, opt=charm_config_opt)

        ret = CheckResult(opt=charm_config_opt)
        if charm_config_opt not in application.get('options', []):
            ret.reason = "using charm config default"
            if self.conf.description:
                ret.reason = f"{ret.reason}: {self.conf.description}"

            return ret

        ret.rc = CheckResult.FAIL
        return ret


@register('skip_if_charm_exists')
class AssertionSkipIfCharmExists(AssertionBase):
    """
    Return True if a charm with the given name exist in the bundle.
    """
    IS_OVERRIDE = True
    OPTS = AssertionOptsCommon

    def __call__(self, charm_config_opt, application):
        if self.conf.skip:
            return CheckResult(rc=CheckResult.SKIPPED, opt=charm_config_opt)

        ret = CheckResult()
        regex_str = self.conf.value
        for app in self.conf.bundle_apps:
            charm = self.conf.bundle_apps[app].get('charm')
            r = re.compile(CHARM_REGEX_TEMPLATE.format(
                regex_str, regex_str, regex_str)).match(charm)
            if r:
                ret.reason = f"charm {charm} found in bundle - skipping check"
                if self.conf.description:
                    ret.reason = f"{ret.reason}: {self.conf.description}"

                return ret

        ret.rc = CheckResult.FAIL
        return ret


@register('assert_ha')
class AssertionAssertHA(AssertionBase):
    """
    Return True if number of units >= expected.
    """
    OPTS = AssertHAAssertionOpts

    def __call__(self, charm_config_opt, application):
        if self.conf.skip:
            return CheckResult(rc=CheckResult.SKIPPED, opt=charm_config_opt)

        num_units = self.get_units(application)
        ret = CheckResult(opt=f"HA (>={self.conf.min_units})")
        if num_units < self.conf.min_units:
            ret.reason = (f"not enough units (value={num_units}, "
                          f"expected='>={self.conf.min_units}')")
            if self.conf.description:
                ret.reason = f"{ret.reason}: {self.conf.description}"

            if self.conf.warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret


@register('assert_channel')
class AssertionAssertChannel(AssertionBase):
    """
    Return True if channel has expected value.
    """
    OPTS = AssertionOptsCommon

    def __call__(self, charm_config_opt, application):
        if self.conf.skip:
            return CheckResult(rc=CheckResult.SKIPPED, opt=charm_config_opt)

        channel = application.get('channel')
        ret = CheckResult(opt=f"charmhub channel ({channel})")
        if not channel:
            if application['charm'].startswith('local:'):
                # no channel expected if its a local charm
                return ret

            ret.reason = ("channel is unset - see "
                          f"{OST_CHARM_CHANNELS_GUIDE_URL}")
            if self.conf.description:
                ret.reason = f"{ret.reason}: {self.conf.description}"

            if self.conf.warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

            return ret

        if self.conf.value is None:
            _ret = re.match(r'.*latest/\S+', channel)
            if not _ret:
                return ret

            channel = _ret.group(0)
        else:
            if self.conf.value == channel:
                return ret

        ret.reason = (f"channel is set to {channel} which is "
                      f"not supported - see {OST_CHARM_CHANNELS_GUIDE_URL}")
        if self.conf.description:
            ret.reason = f"{ret.reason}: {self.conf.description}"

        if self.conf.warn_on_fail:
            ret.rc = CheckResult.WARN
        else:
            ret.rc = CheckResult.FAIL

        return ret


@register('gte')
class AssertionGTE(AssertionBase):
    """
    Return True if option value is >= expected.
    """
    OPTS = AssertionOptsCommon

    def __call__(self, charm_config_opt, application):
        if self.conf.skip:
            return CheckResult(rc=CheckResult.SKIPPED, opt=charm_config_opt)

        if charm_config_opt in application.get('options', {}):
            current = application['options'][charm_config_opt]
        else:
            current = 0

        current = self.atoi(current)
        expected = self.atoi(self.conf.value)
        ret = CheckResult(opt=charm_config_opt,
                          reason=f"value={current}")
        if current < expected:
            ret.reason = f"value={current}, expected={expected}"
            if self.conf.description:
                ret.reason = f"{ret.reason}: {self.conf.description}"

            if self.conf.warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret


@register('neq')
class AssertionNEQ(AssertionBase):
    """
    Return True if option value is != expected.
    """
    OPTS = AssertionOptsCommon

    def __call__(self, charm_config_opt, application):
        if self.conf.skip:
            return CheckResult(rc=CheckResult.SKIPPED, opt=charm_config_opt)

        if charm_config_opt in application.get('options', {}):
            current = application['options'][charm_config_opt]
        else:
            current = 0

        current = self.atoi(current)
        expected = self.atoi(self.conf.value)
        ret = CheckResult(opt=charm_config_opt,
                          reason=f"value={current}")
        if current == expected:
            ret.reason = f"value '{current}' is not valid"
            if self.conf.description:
                ret.reason = f"{ret.reason}: {self.conf.description}"

            if self.conf.warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret


@register('eq')
class AssertionEQ(AssertionBase):
    """
    Return True if option value == expected.
    """
    OPTS = AssertionOptsCommon

    def __call__(self, charm_config_opt, application):
        if self.conf.skip:
            return CheckResult(rc=CheckResult.SKIPPED, opt=charm_config_opt)

        if charm_config_opt in application.get('options', {}):
            current = application['options'][charm_config_opt]
        else:
            current = 0

        current = self.atoi(current)
        expected = self.atoi(self.conf.value)
        ret = CheckResult(opt=charm_config_opt,
                          reason=f"value={current}")
        if current != expected:
            ret.reason = f"value={current}, expected={expected}"
            if self.conf.description:
                ret.reason = f"{ret.reason}: {self.conf.description}"

            if self.conf.warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret


@register('isset')
class AssertionIsSet(AssertionBase):
    """
    Return True if option value is set to a non-default value.
    """
    OPTS = IsSetAssertionOpts

    def __call__(self, charm_config_opt, application):
        if self.conf.skip:
            return CheckResult(rc=CheckResult.SKIPPED, opt=charm_config_opt)

        deprecated_opt = self.conf.supersedes
        extra_info = self.conf.additional_info
        current_value = application.get('options',
                                        []).get(charm_config_opt,
                                                None)
        ret = CheckResult(opt=charm_config_opt,
                          reason=f"value={current_value}")

        deprecated_value = None
        if deprecated_opt:
            deprecated_value = application.get('options',
                                               []).get(deprecated_opt, None)

        if deprecated_value:
            # deprecated option present in the app's config
            if current_value:
                # current option is also set
                ret.reason = (f"{ret.reason}; both "
                              f"'{charm_config_opt}' and "
                              f"'{deprecated_opt}' are set.")
            else:
                # current option not set
                ret = CheckResult(opt=deprecated_opt,
                                  reason=f"value={deprecated_value}")
                ret.reason = (f"{ret.reason}; this option is deprecated. "
                              f"'{charm_config_opt}' should be used "
                              "instead.")
            if extra_info:
                ret.reason = f"{ret.reason} {extra_info}"
            ret.rc = CheckResult.WARN

        elif not current_value:
            # neither deprecated nor current options are set
            ret.reason = "no value set"
            if self.conf.description:
                ret.reason = f"{ret.reason}: {self.conf.description}"

            if self.conf.warn_on_fail:
                ret.rc = CheckResult.WARN
            else:
                ret.rc = CheckResult.FAIL

        return ret


@register('exclusive_backing_dev')
class AssertionExclusiveBackingDev(AssertionBase):
    """
    Return True if charm has an exclusive backing device.
    """
    OPTS = AssertionOptsCommon

    @staticmethod
    def _find_disklabel_users(disks, label):
        devs = []
        for disk in disks:
            if disk['type'] == "bcache":
                backing_dev = disk['backing_device']
                disklabel = re.compile("([a-z0-9]+)-.+").match(backing_dev)
                if disklabel and disklabel[1] == label:
                    devs.append(disk.get('name', "unknown"))

        return devs

    def __call__(self, charm_config_opt, application):
        if self.conf.skip:
            return CheckResult(rc=CheckResult.SKIPPED, opt=charm_config_opt)

        current = application.get('options', [])[charm_config_opt]
        ret = CheckResult(opt=charm_config_opt,
                          reason=f"value={current}")

        with open(self.conf.value, encoding='utf-8') as fd:
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
                    ret.reason = f"bcaches sharing same backing disk: {devs}"
                    if self.conf.description:
                        ret.reason = f"{ret.reason}: {self.conf.description}"

                    if self.conf.warn_on_fail:
                        ret.rc = CheckResult.WARN
                    else:
                        ret.rc = CheckResult.FAIL

        return ret


class LocalAssertionHelpers(AssertionBase):
    """
    Collection of assertions that apply to a Juju bundle.
    """
    @property
    def schema(self):
        return {ASSERTIONS['allow_default'].NAME: {
                    'purpose': 'Allow charm default if config not provided.',
                    'scope': 'config',
                    'source': 'Only supported source type is "bundle"',
                    'value': None},
                ASSERTIONS['skip_if_charm_exists'].NAME: {
                    'purpose': 'Skip check if charm exists',
                    'source': 'Only supported source type is "bundle"',
                    'value': None},
                ASSERTIONS['assert_channel'].NAME: {
                    'purpose':
                        'Ensure application using valid charmhub channel',
                    'scope': 'application',
                    'source': 'This can only be set to "bundle"'},
                ASSERTIONS['assert_ha'].NAME: {
                    'purpose':
                        'Ensure application has minimum number of units',
                    'scope': 'application',
                    'source': 'Only supported source type is "bundle"',
                    'value': None},
                ASSERTIONS['gte'].NAME: {
                    'purpose': 'Ensure option is gte to value'},
                ASSERTIONS['eq'].NAME: {
                    'purpose': 'Ensure option equal to value'},
                ASSERTIONS['neq'].NAME: {
                    'purpose': 'Ensure config option is not set to value'},
                ASSERTIONS['isset'].NAME: {
                    'purpose': ('Ensure config option is set to the provided '
                                'value'),
                    'source': 'Only supported source type is "bundle"',
                    'supersedes': ('Set to the name of a config option that '
                                   'is superseded by this one'),
                    'additional-info': ('Additional information when '
                                        'supersedes option is set')
                }}

    def show_schema(self):
        print(SCHEMA_HEADER)
        for key, _value in self.schema.items():
            print(SCHEMA_ASSERTION_HEADER.format(key=key,
                                                 purpose=_value['purpose']))
            _common_params = {opt.name: opt.opt_description for opt in
                              ASSERTIONS[key].OPTS()
                              if opt.name not in _value}
            _value.update(_common_params)
            del _value['purpose']
            for _param, _param_value in sorted(_value.items()):
                print(f"            {_param}: {_param_value}")

        print("")
