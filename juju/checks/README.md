# Overview

This directory holds the check definitions. This allows you to to say what
checks will be run against which bundle config options based on application
name or charm name - if charm name this means all applications using that
charm will have the same checks run against them.

Assertions are listed by method to run the check and that method must have an
implementation in the check tool. New ones can be added as-and-when.
Assertions can be applied to an application or its config and this is defined
by "scope". The "source" key defines what to check against. If source is
"local" then the bundle setting value is checked against the value in the
assertion. If source is "master", the value is checked against data from
FCE_CONFIG/master.yaml using a regex matching pattern. The "bundle" source
implies that all information needed is within the bundle.

To see the currently supported schema for check definitions do

```
ua-bundle-check.py --schema
```
