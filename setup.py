#!/usr/bin/env python3

from setuptools import setup

setup(
    name='keyer_ui',
    version='1.0',
    description='Premises access solution using MIFARE Classic 1K EV1 - Web UI',
    author='Vitaly Greck',
    author_email='vintozver@ya.ru',
    url='https://github.com/vintozver/keyer_ui/',
    package_dir={'keyer_ui': 'src'},
    #data_files=(
    #    ('static', ('build/static_jquery.js', )),
    #),
    include_package_data=True,
    install_requires=[
        'jinja2', 'pymongo', 'mongoengine',
    ],
    entry_points={
        'console_scripts': [
        ],
    },
)
