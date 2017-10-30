from setuptools import setup
from io import open
import ast


with open('normalization/ufonormalizer.py', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith(u'__version__'):
            version = ast.parse(line).body[0].value.s
            break
    else:
        raise RuntimeError("No __version__ string found!")


setup(name="ufonormalizer",
      version=version,
      description="Example implementation of a UFO normalizer",
      author="Tal Leming",
      author_email="tal@typesupply.com",
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
