from setuptools import setup
from io import open
import ast


with open('src/ufonormalizer.py', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith(u'__version__'):
            version = ast.parse(line).body[0].value.s
            break
    else:
        raise RuntimeError("No __version__ string found!")


setup(
    name="ufonormalizer",
    version=version,
    description=("Script to normalize the XML and other data "
                 "inside of a UFO."),
    author="Tal Leming",
    author_email="tal@typesupply.com",
    url="https://github.com/unified-font-object/ufoNormalizer",
    package_dir={"": "src"},
    py_modules=['ufonormalizer'],
    entry_points={
        'console_scripts': [
            "ufonormalizer = ufonormalizer:main",
        ]
    },
    test_suite="tests",
    license="OpenSource, BSD-style",
    platforms=["Any"],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Environment :: Other Environment",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "Topic :: Text Processing :: Fonts",
        "Topic :: Multimedia :: Graphics",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
    ],
)
