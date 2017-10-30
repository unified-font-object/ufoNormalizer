from setuptools import setup
from normalization.ufonormalizer import __version__

setup(name="ufonormalizer",
      version=__version__,
      description="Example implementation of a UFO normalizer",
      author="Tal Leming",
      email="tal@typesupply.com",
      url="https://github.com/unified-font-object/ufoNormalizer",
      package_dir={"": "normalization"},
      py_modules=['ufonormalizer'],
      entry_points={
          'console_scripts': [
              "ufonormalizer = ufonormalizer:main",
              ]
          },
      test_suite="normalization"
      )
