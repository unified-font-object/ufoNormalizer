from setuptools import setup

setup(name="ufonormalizer",
      version="0.1",
      description="Example implementation of a UFO normalizer",
      author="Tal Leming",
      email="tal@typesupply.com",
      url="https://github.com/unified-font-object/ufo-example-implementations",
      package_dir={"": "normalization"},
      py_modules=['ufonormalizer'],
      entry_points={
          'console_scripts': [
              "ufonormalizer = ufonormalizer:main",
              ]
          }
      )
