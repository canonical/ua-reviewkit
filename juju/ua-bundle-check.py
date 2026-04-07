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

import os
import sys
import argparse

from ua_bundle_checker.checker import setup


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--type', '-t', type=str, default=None,
                        required=False,
                        help=("The type of bundle we are checking. This name "
                         "maps to a file under the 'checks' directory. Some "
                         "checks support more than one variant of a product "
                         "and so have more than one subgroup. To specify the "
                         "group suffix the type name with a colon then the "
                         "group name e.g. :<group>. If more than one group "
                         "exists but none are specified, the first one found "
                         "will be used. If not provided, a generic check "
                         "covering all charms in the bundle is performed."))
    parser.add_argument('--fce-config', type=str,
                        required=False, help="Path to FCE config.")
    parser.add_argument('--bundle', '-b', type=str,
                        required=False, help="Path to alternate bundle. "
                        "Default is to use $FCE_CONFIG/bundle.yaml")
    parser.add_argument('--errors-only', action='store_true', default=False,
                        help="Exclude [PASS] info.")
    parser.add_argument('--quiet', '-q', action='store_true', default=False)
    parser.add_argument('--schema', action='store_true', default=False)
    parser.add_argument('--checks-path', type=str,
                        default=os.path.join(os.path.dirname(__file__),
                                             'checks'))
    setup(parser.parse_args())

