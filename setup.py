from setuptools import setup

setup(name="ufonormalizer",
      version="0.1",
      description="Example implementations of various portions of the UFO Specification.",
      author="Unified Font Object",
      url="https://github.com/unified-font-object/ufo-example-implementations",
      package_dir={"": "normalization"},
      py_modules=['ufonormalizer'],
      entry_points={
          'console_scripts': [
              "ufonormalizer = ufonormalizer:main",
              ]
          }
      )
