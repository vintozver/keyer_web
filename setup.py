from io import BytesIO
from pathlib import Path
from shutil import copytree
from urllib.request import urlopen
from zipfile import ZipFile

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


STATIC_URLS = {
    "sprintf.js": "https://raw.githubusercontent.com/alexei/sprintf.js/1.1.2/dist/sprintf.min.js",
    "jquery.js": "https://code.jquery.com/jquery-3.6.0.min.js",
}

ARCHIVE_URLS = {
    "https://jqueryui.com/resources/download/jquery-ui-1.14.1.zip": [
        ("jquery-ui.min.css", "jquery-ui/main.css"),
        ("jquery-ui.structure.min.css", "jquery-ui/structure.css"),
        ("jquery-ui.theme.min.css", "jquery-ui/theme.css"),
        ("jquery-ui.min.js", "jquery-ui/main.js"),
        ("images/", "jquery-ui/images/"),
    ],
}


class build_py(_build_py):
    def run(self):
        super().run()
        package_dir = Path(self.build_lib) / "keyer_web"
        for directory in ("config", "handler", "module", "util", "template"):
            copytree(Path("src") / directory, package_dir / directory, dirs_exist_ok=True)
        static_dir = package_dir / "static"

        for relative_path, url in STATIC_URLS.items():
            destination = static_dir / relative_path
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(urlopen(url).read())

        for url, actions in ARCHIVE_URLS.items():
            missing = [
                target for source, target in actions
                if (source.endswith("/") and not (static_dir / target).is_dir())
                or (not source.endswith("/") and not (static_dir / target).exists())
            ]
            if missing:
                with ZipFile(BytesIO(urlopen(url).read())) as archive:
                    members = archive.namelist()
                    source = next(
                        (source for source, _ in actions if not source.endswith("/")),
                        actions[0][0].rstrip("/"),
                    )
                    marker = "/%s" % source
                    member = next(
                        member for member in members
                        if member.endswith(marker) or marker + "/" in member
                    )
                    prefix = member.split(marker, 1)[0]
                    for source, target in actions:
                        archive_path = "%s/%s" % (prefix, source.rstrip("/"))
                        if source.endswith("/"):
                            source_prefix = "%s/" % archive_path
                            for member in members:
                                if member.startswith(source_prefix) and not member.endswith("/"):
                                    destination = static_dir / target / member[len(source_prefix):]
                                    if not destination.exists():
                                        destination.parent.mkdir(parents=True, exist_ok=True)
                                        destination.write_bytes(archive.read(member))
                        else:
                            destination = static_dir / target
                            if not destination.exists():
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                destination.write_bytes(archive.read(archive_path))


setup(
    cmdclass={"build_py": build_py},
)
