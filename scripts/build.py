"""Build and validate PilotPatch release files from the checked-in source."""

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import tarfile
import tomllib
import venv
import xml.etree.ElementTree as xml
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EDGE = ROOT / "editors/edge"
EDITOR = ROOT / "editors/vscode"
EDGE_FILES = (
    "background.js",
    "connection.js",
    "content.js",
    "manifest.json",
    "popup.css",
    "popup.html",
    "popup.js",
)
BUILD_TOOL = "build==1.6.1"


def run(python, *args):
    subprocess.run([str(python), "-I", *args], cwd=ROOT, check=True)


def build_python(stage, requirements, index):
    # Use the existing interpreter when it already has the pinned build tools.
    check = "; ".join(
        f"assert version({name!r}) == {version!r}"
        for name, version in (item.split("==") for item in requirements)
    )
    python = Path(sys.executable)
    result = subprocess.run(
        [str(python), "-I", "-c", f"from importlib.metadata import version; {check}"],
        capture_output=True,
    )
    if result.returncode:
        environment = stage / "build-env"
        venv.create(environment, with_pip=True)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        run(python, "-m", "pip", "install", *index, *requirements)
    run(python, "-m", "build", "--no-isolation", "--outdir", str(stage))
    return python


def write_zip(target, files):
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for name, source in sorted(files.items()):
            if isinstance(source, Path):
                archive.write(source, name)
            else:
                archive.writestr(name, source)
    with ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != files.keys():
            raise ValueError(f"Could not verify {target.name}")


def build_vsix(target, manifest):
    # PilotPatch is plain JavaScript. Require an explicit packaging change if it
    # gains runtime dependencies or starts shipping new asset types.
    if manifest.get("dependencies") or manifest.get("extensionDependencies"):
        raise ValueError("The VSIX builder supports dependency-free editor extensions.")
    files = {"extension/package.json": EDITOR / "package.json"}
    for name in manifest["files"]:
        path = (EDITOR / name).resolve()
        if not path.is_relative_to(EDITOR) or not path.is_file():
            raise ValueError(f"Invalid or missing VSIX file: {name}")
        files[f"extension/{PurePosixPath(name).as_posix()}"] = path
    files["extension/readme.md"] = files.pop("extension/README.md")
    files["extension/LICENSE.txt"] = files.pop("extension/LICENSE")
    if f"extension/{manifest['main'].removeprefix('./')}" not in files:
        raise ValueError("The VSIX is missing the extension entry point.")

    # Open Packaging Conventions and the VS Code VSIX manifest.
    package = xml.Element(
        "PackageManifest",
        Version="2.0.0",
        attrib={
            "xmlns": "http://schemas.microsoft.com/developer/vsx-schema/2011",
        },
    )
    metadata = xml.SubElement(package, "Metadata")
    xml.SubElement(
        metadata,
        "Identity",
        Id=manifest["name"],
        Publisher=manifest["publisher"],
        Version=manifest["version"],
        Language="en-US",
    )
    xml.SubElement(metadata, "DisplayName").text = manifest["displayName"]
    xml.SubElement(metadata, "Description").text = manifest["description"]
    xml.SubElement(metadata, "Categories").text = ",".join(manifest["categories"])
    xml.SubElement(metadata, "GalleryFlags").text = "Public"
    xml.SubElement(metadata, "License").text = "extension/LICENSE.txt"
    properties = xml.SubElement(metadata, "Properties")
    for name, value in {
        "Engine": manifest["engines"]["vscode"],
        "ExtensionKind": ",".join(manifest["extensionKind"]),
        "ExecutesCode": "true",
    }.items():
        xml.SubElement(
            properties, "Property", Id=f"Microsoft.VisualStudio.Code.{name}", Value=value
        )
    xml.SubElement(
        xml.SubElement(package, "Installation"),
        "InstallationTarget",
        Id="Microsoft.VisualStudio.Code",
    )
    xml.SubElement(package, "Dependencies")
    assets = xml.SubElement(package, "Assets")
    for asset, path in {
        "Microsoft.VisualStudio.Code.Manifest": "extension/package.json",
        "Microsoft.VisualStudio.Services.Content.Details": "extension/readme.md",
        "Microsoft.VisualStudio.Services.Content.License": "extension/LICENSE.txt",
    }.items():
        xml.SubElement(assets, "Asset", Type=asset, Path=path, Addressable="true")
    files["extension.vsixmanifest"] = xml.tostring(package, encoding="utf-8", xml_declaration=True)
    types = xml.Element(
        "Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types"
    )
    mime = {
        "css": "text/css",
        "js": "application/javascript",
        "json": "application/json",
        "md": "text/markdown",
        "svg": "image/svg+xml",
        "txt": "text/plain",
        "vsixmanifest": "text/xml",
    }
    for suffix in sorted({PurePosixPath(name).suffix[1:] for name in files}):
        xml.SubElement(types, "Default", Extension=suffix, ContentType=mime[suffix])
    files["[Content_Types].xml"] = xml.tostring(types, encoding="utf-8", xml_declaration=True)
    write_zip(target, files)


def build_office(python, stage, index, sdist, wheel, vsix, edge_zip, target):
    print("Collecting locked Windows x64 wheels for Python 3.11, 3.12 and 3.13.", flush=True)
    wheelhouse = stage / "wheelhouse"
    # Evaluate markers for the target interpreter before invoking pip. pip's
    # --python-version selects wheel tags but evaluates markers on the build host.
    script = (
        "import sys; from pathlib import Path; from packaging.requirements import Requirement;"
        " version, output = sys.argv[1:];"
        " reqs = [Requirement(line) for line in Path('requirements.txt').read_text().splitlines()"
        " if line.strip() and not line.lstrip().startswith('#')];"
        " env = {'python_version': version, 'python_full_version': version+'.0',"
        " 'sys_platform':'win32', 'platform_system':'Windows', 'platform_machine':'AMD64'};"
        " Path(output).write_text(''.join(f'{req.name}{req.specifier}\\n' for req in reqs"
        " if not req.marker or req.marker.evaluate(env)), encoding='utf-8')"
    )
    for version in ("3.11", "3.12", "3.13"):
        lock = stage / f"requirements-{version}.txt"
        run(python, "-c", script, version, str(lock))
        run(
            python,
            "-m",
            "pip",
            "download",
            *index,
            "--quiet",
            "--only-binary=:all:",
            "--platform",
            "win_amd64",
            "--python-version",
            version,
            "--implementation",
            "cp",
            "--abi",
            "cp" + version.replace(".", ""),
            "--dest",
            str(wheelhouse),
            "-r",
            str(lock),
        )

    with tarfile.open(sdist) as archive:
        files = {
            member.name.split("/", 1)[1]: archive.extractfile(member).read()
            for member in archive.getmembers()
            if member.isfile()
        }
    files.update(
        {
            f"dist/{wheel.name}": wheel,
            f"artifacts/{vsix.name}": vsix,
            f"artifacts/{edge_zip.name}": edge_zip,
        }
    )
    files.update({f"wheelhouse/{path.name}": path for path in wheelhouse.glob("*.whl")})
    write_zip(target, files)


def main():
    parser = argparse.ArgumentParser(
        prog="build.cmd",
        description=__doc__,
        epilog="Packages are saved in the artifacts folder beside build.cmd.",
    )
    parser.add_argument("--no-office", action="store_true", help="Skip the offline Windows bundle.")
    parser.add_argument("--wheelhouse", type=Path, help="Use only this local directory for pip.")
    options = parser.parse_args()
    if (
        not (3, 11) <= sys.version_info < (3, 14)
        or sys.maxsize <= 2**32
        or sys.implementation.name != "cpython"
    ):
        parser.error("64-bit CPython 3.11–3.13 is required.")
    index = []
    if options.wheelhouse:
        if not options.wheelhouse.is_dir():
            parser.error("--wheelhouse must name a directory containing approved wheels.")
        index = ["--no-index", "--find-links", str(options.wheelhouse.resolve())]
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    editor = json.loads((EDITOR / "package.json").read_bytes())
    edge = json.loads((EDGE / "manifest.json").read_bytes())
    lock = json.loads((EDITOR / "package-lock.json").read_bytes())
    source = ast.parse((ROOT / "pilotpatch/__init__.py").read_text(encoding="utf-8"))
    runtime = next(
        ast.literal_eval(node.value)
        for node in source.body
        if isinstance(node, ast.Assign)
        and any(isinstance(name, ast.Name) and name.id == "__version__" for name in node.targets)
    )
    if {runtime, editor["version"], edge["version"], lock["version"]} != {version}:
        parser.error("The Python, VS Code and Edge package versions must match.")
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix=".build-", dir=artifacts) as temporary:
        stage = Path(temporary)
        print("Building Python wheel and source archive.", flush=True)
        python = build_python(stage, [BUILD_TOOL, *project["build-system"]["requires"]], index)
        wheel = stage / f"pilotpatch-{version}-py3-none-any.whl"
        sdist = stage / f"pilotpatch-{version}.tar.gz"
        vsix = stage / f"pilotpatch-{version}.vsix"
        edge_zip = stage / f"PilotPatch-Edge-{version}.zip"
        build_vsix(vsix, editor)
        write_zip(edge_zip, {name: EDGE / name for name in EDGE_FILES})
        with ZipFile(wheel) as archive:
            if archive.testzip() is not None:
                raise ValueError("The Python wheel is corrupt.")
            for name in EDGE_FILES:
                if archive.read(f"pilotpatch/edge_extension/{name}") != (EDGE / name).read_bytes():
                    raise ValueError(f"The Python wheel has stale Edge assets: {name}")
        with tarfile.open(sdist) as archive:
            for name in ("build.cmd", "scripts/build.py", "editors/vscode/package-lock.json"):
                archive.getmember(f"pilotpatch-{version}/{name}")
        outputs = [
            ("Python install wheel", wheel),
            ("Python source archive", sdist),
            ("VS Code extension installer", vsix),
            ("Edge extension ZIP for distribution", edge_zip),
        ]
        if not options.no_office:
            office = stage / f"PilotPatch-Office-{version}.zip"
            build_office(python, stage, index, sdist, wheel, vsix, edge_zip, office)
            checksum = office.with_suffix(".zip.sha256")
            with office.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            checksum.write_text(f"{digest}  {office.name}\n", encoding="ascii")
            outputs.extend([("Offline Windows bundle", office), ("Bundle SHA-256", checksum)])
        for label, path in outputs:
            target = artifacts / path.name
            path.replace(target)
            print(f"{label} saved to {target}", flush=True)
        print(
            r"For Edge's Load unpacked dialog, run .\setup-windows.ps1 and select the "
            "edge-extension folder it prints. That folder contains manifest.json.",
            flush=True,
        )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Build failed: {exc}")
