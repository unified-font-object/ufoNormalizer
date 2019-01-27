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

Note: if you are working on a UFO within RoboFont and run ufoNormalizer on that UFO, RoboFont will notify you that the UFO has been updated externally. Simply accept this by selecting "Update."

## Automatic usage

ufoNormalizer is much more useful if used in an automated manner, so you don't have to think about it. 

Two methods of this are 
1. Using withing a Git hook
2. Enabling RoboFont's preference for normalizing on save

### Using in a Git hook

> Git hooks are scripts that Git executes before or after events such as: commit, push, and receive. Git hooks are a built-in feature - no need to download anything. Git hooks are run locally.
– from [Git Hooks](https://githooks.com/)

It's easy to set up a git hook that will normalize ufos in a project immediately before each commit, ensuring that you only ever commit clean UFO data.

In your project, navigate to `/.git/hooks` and replace `pre-commit.sample` with the following code, then remove the file extension:

```bash
#!/bin/sh

# A hook script to verify what is about to be committed.
# Called by "git commit" with no arguments.
#
# Uses bash syntax to call arguments as needed.
#
# To enable this hook, save this to <your_project>/.git/hooks/pre-commit (with no file extension)

set -e

for ufo in ./*.ufo; do
    ufonormalizer "$ufo"
done
```

Now, each time you commit, all `.ufo`s in your Git project will be normalized before being recorded by Git.

### Enabling RoboFont's preference for normalizing on save

If you are working within RoboFont, you can set it to normalize UFOs on save.

Simply open the Scripting Window and run the following code:

```
setDefault("shouldNormalizeOnSave", True)
```

