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

from collections import UserList
from dataclasses import dataclass


@dataclass
class AssertionOpt:
    """ Represents an assertion option. """
    name: str = None
    opt_type: type = None
    value: object = None
    opt_description: str = None


class AssertionOptsBase(UserList):
    """ Base class for all assertion opt collections. """

    def __getattr__(self, name):
        if name != 'data':
            name = name.replace('_', '-')
            for opt in self:
                if opt.name == name:
                    return opt.value

        raise AttributeError(f"no opt found with name {name}")

    def __setattr__(self, name, value):
        """
        This permits setting arbitrary attributes which is required for
        commuting custom args to commands.
        """
        if name != 'data':
            for opt in self:
                if opt.name == name:
                    opt.value = value
                    return

        super().__setattr__(name, value)


class AssertionOptsCommon(AssertionOptsBase):
    """ Assertion options common to all types. """

    def __init__(self, data=None):
        if not data:
            data = []

        super().__init__(data + [
            AssertionOpt('source', str, None,
                         'Set to one of [local|bundle|master]'),
            AssertionOpt('scope', str, None,
                         'Set to one of [config|application]'),
            AssertionOpt('value', str, None,
                         ('Value we are checking against. Note that if '
                          'source=master this must be regex with '
                          'single substring match')),
            AssertionOpt('warn-on-fail', bool, False,
                         'Set to True if you want a warning when assertion '
                         'fails (default is False)'),
            AssertionOpt('skip', bool, False, 'Set to True if you want to '
                         'skip this assertion'),
            AssertionOpt('description', str, None,
                         'Describes what this assertion is doing')])


class IsSetAssertionOpts(AssertionOptsCommon):
    """ Assertion options for the IsSet assertion. """

    def __init__(self, data=None):
        if not data:
            data = []

        super().__init__(data + [AssertionOpt('additional-info', str, None,
                         'Set to one of [local|bundle|master]'),
                         AssertionOpt('supersedes', str, None, '')])


class AssertHAAssertionOpts(AssertionOptsCommon):
    """ Assertion options for the AssertHA assertion. """

    def __init__(self, data=None):
        min_units = 3
        if not data:
            data = []

        super().__init__(data + [AssertionOpt('min-units', int, min_units,
                         'Minimum number of units the application must have. '
                         f'Default is {min_units}')])
