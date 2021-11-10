import unittest

from ua_bundle_checker.checker import (
    CheckResult,
    AssertionBase,
)


class TestJujuBundleChecker(unittest.TestCase):

    def test_check_result_pass(self):
        c = CheckResult()
        self.assertTrue(c.passed)

    def test_check_result_fail(self):
        c = CheckResult(CheckResult.FAIL)
        self.assertFalse(c.passed)

    def test_assertion_base_atoi(self):
        self.assertEquals(AssertionBase().atoi("100k"), 100 * 1000)
        self.assertEquals(AssertionBase().atoi("100K"), 100 * 1024)
        self.assertEquals(AssertionBase().atoi("100m"), 100 * 1000 ** 2)
        self.assertEquals(AssertionBase().atoi("100M"), 100 * 1024 ** 2)
        self.assertEquals(AssertionBase().atoi("100g"), 100 * 1000 ** 3)
        self.assertEquals(AssertionBase().atoi("100G"), 100 * 1024 ** 3)

    def test_assertion_base_get_units(self):
        app = {'num_units': 3}
        self.assertEquals(AssertionBase().get_units(app), 3)
        app = {'scale': 3}
        self.assertEquals(AssertionBase().get_units(app), 3)
        app = {}
        self.assertEquals(AssertionBase().get_units(app), None)
