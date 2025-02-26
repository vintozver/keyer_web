#!/usr/bin/env python3

import io
import os
import os.path
import setuptools
import setuptools.command.build
import urllib.request
import zipfile


class ExtraStaticFiles(setuptools.Command):
    _loc_sprintf_js = "https://raw.githubusercontent.com/alexei/sprintf.js/refs/heads/master/src/sprintf.js"
    _f_sprintf_js = "sprintf.js"
    _loc_jquery_js = "https://code.jquery.com/jquery-3.6.0.js"
    _f_jquery_js = "jquery.js"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.build_lib = None
        self.editable_mode = False

    def initialize_options(self):
        pass

    def finalize_options(self):
        self.set_undefined_options("build_py", ("build_lib", "build_lib"))

    def run(self):
        pkgs = list(self.distribution.package_dir.keys())
        assert len(pkgs) == 1, "Only one package shall be defined"
        pkg = pkgs[0]

        try:
            os.makedirs(os.path.join(self.build_lib, pkg, "static"))
        except OSError:
            pass

        _content_sprintf_js = urllib.request.urlopen(self._loc_sprintf_js).read()
        with open(os.path.join(self.build_lib, pkg, "static", self._f_sprintf_js), "wb") as _file_sprintf_js:
            _file_sprintf_js.write(_content_sprintf_js)

        _content_jquery_js = urllib.request.urlopen(self._loc_jquery_js).read()
        with open(os.path.join(self.build_lib, pkg, "static", self._f_jquery_js), "wb") as _file_jquery_js:
            _file_jquery_js.write(_content_jquery_js)

        try:
            os.makedirs(os.path.join(self.build_lib, pkg, "static", "jquery-ui"))
        except OSError:
            pass

        _zf_buffer = io.BytesIO(urllib.request.urlopen("https://jqueryui.com/resources/download/jquery-ui-1.14.1.zip").read())
        with zipfile.ZipFile(_zf_buffer, 'r') as _zf_jquery_ui:
            _b = _zf_jquery_ui.read("jquery-ui-1.14.1/jquery-ui.min.css")
            with open(os.path.join(self.build_lib, pkg, "static", "jquery-ui", "main.css"), "wb") as _f:
                _f.write(_b)
            _b = _zf_jquery_ui.read("jquery-ui-1.14.1/jquery-ui.structure.min.css")
            with open(os.path.join(self.build_lib, pkg, "static", "jquery-ui", "structure.css"), "wb") as _f:
                _f.write(_b)
            _b = _zf_jquery_ui.read("jquery-ui-1.14.1/jquery-ui.theme.min.css")
            with open(os.path.join(self.build_lib, pkg, "static", "jquery-ui", "theme.css"), "wb") as _f:
                _f.write(_b)
            _b = _zf_jquery_ui.read("jquery-ui-1.14.1/jquery-ui.min.js")
            with open(os.path.join(self.build_lib, pkg, "static", "jquery-ui", "main.js"), "wb") as _f:
                _f.write(_b)
            _images_dir = os.path.join(self.build_lib, pkg, "static", "jquery-ui", "images")
            try:
                os.makedirs(_images_dir)
            except OSError:
                pass
            for _zf_name in _zf_jquery_ui.namelist():
                _prefix = "jquery-ui-1.14.1/images/"
                if _zf_name.startswith(_prefix):
                    _b = _zf_jquery_ui.read(_zf_name)
                    _zf_name = _zf_name.removeprefix(_prefix)
                    with open(os.path.join(_images_dir, _zf_name), "wb") as _f:
                        _f.write(_b)


setuptools.command.build.build.sub_commands.append(("build_static_extra", None))


setuptools.setup(
    name='keyer_web',
    version='1.0',
    description='Premises access solution using MIFARE Classic 1K EV1 - frontend and backend',
    author='Vitaly Greck',
    author_email='vintozver@ya.ru',
    url='https://github.com/vintozver/keyer_web/',
    cmdclass={'build_static_extra': ExtraStaticFiles},
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
