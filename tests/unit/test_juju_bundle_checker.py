import re
import unittest

from ua_bundle_checker.assertion.commands import (
    CheckResult,
    AssertionBase,
    CHARM_REGEX_TEMPLATE
)

id_url_samples = {
    "aodh": {
        "should_match": (
            "local:aodh", "local:aodh-22", "cs:aodh-42",
            "ch:aodh-42", "/home/admincloud/domaine-op-146944/charms/aodh",
            "/home/s.maas_fcb.dev/openstack-charms/xenial/aodh-66"
        ),
        "should_not_match": (
            "local:aodh-ha", "local:aodh-ha-44", "cs:aodh-ha", "cs:aodh-ha-44",
            "ch:aodh-ha", "ch:aodh-ha-44", "./aodh-ha", "./aodh-ha-44",
            "/home/ubuntu/aodh-ha", "/home/ubuntu-user/aodh-ha-44"
        )
    },
    "apache2": {
        "should_match": (
            "local:apache2", "local:apache2-22", "cs:apache2-42",
            "ch:apache2-42",
            "/home/admincloud/domaine-op-146944/charms/apache2",
            "/home/s.maas_fcb.dev/openstack-charms/xenial/apache2-66",
            "./xenial/apache2-66", "cs:~erlon/apache2", "cs:~erlon/apache2-23",
            "cs:~openstack-next/apache2-23"
        ),
        "should_not_match": ("apache2-proxy", "/home/apache2/ceph-mon-23")
    }
}


class TestJujuBundleChecker(unittest.TestCase):
    """ Tests for the Juju bundle checker """

    def test_check_result_pass(self):
        c = CheckResult()
        self.assertTrue(c.passed)

    def test_check_result_fail(self):
        c = CheckResult(CheckResult.FAIL)
        self.assertFalse(c.passed)

    def test_assertion_base_atoi(self):
        self.assertEqual(AssertionBase({}).atoi("100k"), 100 * 1000)
        self.assertEqual(AssertionBase({}).atoi("100K"), 100 * 1024)
        self.assertEqual(AssertionBase({}).atoi("100m"), 100 * 1000 ** 2)
        self.assertEqual(AssertionBase({}).atoi("100M"), 100 * 1024 ** 2)
        self.assertEqual(AssertionBase({}).atoi("100g"), 100 * 1000 ** 3)
        self.assertEqual(AssertionBase({}).atoi("100G"), 100 * 1024 ** 3)

    def test_assertion_base_get_units(self):
        app = {'num_units': 3}
        self.assertEqual(AssertionBase({}).get_units(app), 3)
        app = {'scale': 3}
        self.assertEqual(AssertionBase({}).get_units(app), 3)
        app = {}
        self.assertEqual(AssertionBase({}).get_units(app), 1)


class TestCharmNameRegex(unittest.TestCase):
    """ Tests for the Juju bundle checker charm name regex. """

    def test_regex(self):
        for app_name, asserts in id_url_samples.items():
            for sample in asserts['should_match']:
                r = re.compile(
                    CHARM_REGEX_TEMPLATE.format(
                        app_name, app_name, app_name)).match(sample)
                msg = f"App '{app_name}' should match with {sample}"
                self.assertIsNotNone(r, msg)

            for sample in asserts['should_not_match']:
                r = re.compile(
                    CHARM_REGEX_TEMPLATE.format(
                        app_name, app_name, app_name)).match(sample)
                msg = f"App '{app_name}' should not match with {sample}"
                self.assertIsNone(r, msg)
