"""Test package bootstrap.

The library uses a ``src/`` layout, so when the tests are run directly with
``python3 -m unittest discover -s tests`` (without first installing the
package) the ``src`` directory needs to be importable. Adding it to
``sys.path`` here keeps the test suite runnable with only the standard library.
"""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
