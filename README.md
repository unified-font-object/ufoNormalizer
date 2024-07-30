[![Coverage Status](https://coveralls.io/repos/unified-font-object/ufoNormalizer/badge.svg?branch=master&service=github)](https://coveralls.io/github/unified-font-object/ufoNormalizer?branch=master)
![Python Versions](https://img.shields.io/badge/python-3.7%2C%203.8%2C%203.9%2C%203.10%2C%203.11-blue.svg)
[![PyPI Version](https://img.shields.io/pypi/v/ufonormalizer.svg)](https://pypi.python.org/pypi/ufonormalizer)

# ufoNormalizer

Provides a standard formatting so that there are meaningful diffs in version control rather than formatting noise.

Examples of formatting applied by ufoNormalizer include:
- Changing floating-point numbers to integers where it doesn't alter the value (e.g. `x="95.0"` becomes `x="95"` )
- Rounding floating-point numbers to 10 digits
- Formatting XML with tabs rather than spaces

## Usage in RoboFont

RoboFont comes with ufoNormalizer pre-installed, and you can set a preference to normalize UFOs on save.

Simply open the Scripting Window and run the following code:

```
from mojo.UI import setDefault, getDefault

setDefault("shouldNormalizeOnSave", True)

print("shouldNormalizeOnSave is set to " + str(getDefault("shouldNormalizeOnSave")))
```

## Advanced usage

### Installation

Install these tools using the [pip](https://pip.pypa.io/en/stable/installing/) package [hosted on PyPI](https://pypi.org/project/ufonormalizer/):

```
pip install --upgrade ufonormalizer
```

### Command line

Use on the command line:

```
ufonormalizer <path>/font.ufo
```

To view all arguments, run:

```
ufonormalizer --help
```

Note: if you are working on a UFO within RoboFont and run ufoNormalizer on that UFO, RoboFont will notify you that the UFO has been updated externally. Simply accept this by selecting "Update."

### Automating via Git hooks

Beyond basic command-line usage, ufoNormalizer can be used in an automated manner. 

Of course, you can automate it to run from a shell script or a Python script. One useful possibility is using it within a Git hook.

> Git hooks are scripts that Git executes before or after events such as: commit, push, and receive. Git hooks are a built-in feature - no need to download anything. Git hooks are run locally.
– from [Git Hooks](https://githooks.com/)

It's easy to set up a git hook that will normalize ufos in a project immediately before each commit, ensuring that you only ever commit clean UFO data.

In a Git project, navigate to `/.git/hooks` and replace `pre-commit.sample` with the following code, then remove the file extension:

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

Because this hook is setup within the immediate project, this configuration will only apply to the immediate project. You will need to update each project to use this Git hook if you wish to normalize UFOs elsewhere. If you want this hook to be added to all future git projects, you can [configure a global git template](https://coderwall.com/p/jp7d5q/create-a-global-git-commit-hook). However, this approach probably doesn't make sense if you also work on projects that don't involve UFO files. 
