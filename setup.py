#!/usr/bin/env python3

from setuptools import setup

setup(
    name='keyer_web',
    version='1.0',
    description='Premises access solution using MIFARE Classic 1K EV1 - frontend and backend',
    author='Vitaly Greck',
    author_email='vintozver@ya.ru',
    url='https://github.com/vintozver/keyer_web/',
    package_dir={'keyer_web': 'src'},
    include_package_data=True,
    install_requires=[
        'jinja2', 'pymongo', 'mongoengine', 'aiodns', 'aiohttp',
    ],
    entry_points={
        'console_scripts': [
        ],
    },
)
