[![Build Status](https://travis-ci.org/unified-font-object/ufoNormalizer.svg)](https://travis-ci.org/unified-font-object/ufoNormalizer)
[![Build status](https://ci.appveyor.com/api/projects/status/pc4l0dryn5hevcw4?svg=true)](https://ci.appveyor.com/project/miguelsousa/ufonormalizer)
[![Coverage Status](https://coveralls.io/repos/unified-font-object/ufoNormalizer/badge.svg?branch=master&service=github)](https://coveralls.io/github/unified-font-object/ufoNormalizer?branch=master)
![Python Versions](https://img.shields.io/badge/python-2.7%2C%203.4%2C%203.5-blue.svg)
[![PyPI Version](https://img.shields.io/pypi/v/ufonormalizer.svg)](https://pypi.python.org/pypi/ufonormalizer)

# ufoNormalizer

Provides a standard formatting so that there are meaningful diffs in version control rather than formatting noise.

Examples of formatting changes include:
- Changing floating-point numbers to integers where it doesn't alter the value (e.g. `x="95.0"` becomes `x="95"` )
- Rounding floating-point numbers to 10 digits
- Formatting XML with tabs rather than spaces

## Installation

Install these tools using the [pip](https://pip.pypa.io/en/stable/installing/) package [hosted on PyPI](https://pypi.org/project/ufonormalizer/):

```
pip install --upgrade ufonormalizer
```

## Basic usage

Use on the command line:

```
ufonormalizer <path>/font.ufo
```

To view all arguments, run:

```
ufonormalizer --help
```