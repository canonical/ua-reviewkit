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
                         'Set to one of [local|bundle]. If source is set to '
                         'local the value compared will be the one from the '
                         'assertion definition otherwise if set to bundle the '
                         'will be taken from the bundle.'),
            AssertionOpt('scope', str, None,
                         'Defines whether or not the assertion applies to an '
                         'entire charm application or just one of its config '
                         'options. Set to one of [config|application]'),
            AssertionOpt('value', str, None,
                         'Value we are checking against.'),
            AssertionOpt('warn-on-fail', bool, False,
                         'Set to True if you want a warning when assertion '
                         'fails (default is False)'),
            AssertionOpt('regex', bool, False,
                         'If True the value will be treated as a regular '
                         'expression.'),
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
                                              'When the assertion is run the '
                                              'output can optionally contain '
                                              'additional information as '
                                              'provided by this option.'),
                                 AssertionOpt('supersedes', str, None,
                                              'If a charm config option has '
                                              'been deprecated this can be '
                                              'used to define assertions for '
                                              'both but indicate that the '
                                              'deprecated option has be '
                                              'switched to the newer one.')])


class AssertHAAssertionOpts(AssertionOptsCommon):
    """ Assertion options for the AssertHA assertion. """

    def __init__(self, data=None):
        min_units = 3
        if not data:
            data = []

        msg = ('Minimum number of units the application must have. Default '
               f'is {min_units}')
        super().__init__(data + [AssertionOpt('min-units', int, min_units,
                                              msg)])
