from setuptools import setup, find_packages


setup(
    name="ufonormalizer",
    description=("Script to normalize the XML and other data "
                 "inside of a UFO."),
    author="Tal Leming",
    author_email="tal@typesupply.com",
    url="https://github.com/unified-font-object/ufoNormalizer",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    entry_points={
        'console_scripts': [
            "ufonormalizer = ufonormalizer:main",
        ]
    },
    use_scm_version={
        "write_to": 'src/ufonormalizer/_version.py',
        "write_to_template": '__version__ = "{version}"',
    },
    setup_requires=['setuptools_scm'],
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
        "Programming Language :: Python :: 3",
        "Topic :: Text Processing :: Fonts",
        "Topic :: Multimedia :: Graphics",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
    ],
    python_requires='>=3.6',
    zip_safe=True,
)
