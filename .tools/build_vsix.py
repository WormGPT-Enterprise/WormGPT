"""Build a VSIX from vscode-extension/ (no vsce needed).

A VSIX is a ZIP with:
  extension.vsixmanifest      - VS Marketplace metadata
  [Content_Types].xml         - OPC content types
  extension/**                - the extension itself
The compiled JS in out/ is what ships; src/ is included for reference.
"""
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "vscode-extension"
DIST = EXT / "dist"

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".md" ContentType="text/x-markdown"/>
  <Default Extension=".txt" ContentType="text/plain"/>
  <Default Extension=".map" ContentType="application/json"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
"""


def manifest(pkg: dict) -> str:
    engine = pkg.get("engines", {}).get("vscode", "*")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{pkg['name']}" Version="{pkg['version']}" Publisher="{pkg['publisher']}"/>
    <DisplayName>{pkg['displayName']}</DisplayName>
    <Description xml:space="preserve">{pkg['description']}</Description>
    <Categories>{','.join(pkg.get('categories', []))}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{engine}" />
      <Property Id="Microsoft.VisualStudio.Services.GitHubFlavoredMarkdown" Value="true" />
    </Properties>
    <License>extension/LICENSE.txt</License>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE.txt" Addressable="true" />
  </Assets>
</PackageManifest>
"""


def collect() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for name in ("package.json", "README.md", "LICENSE.txt"):
        files.append((EXT / name, f"extension/{name}"))
    for path in sorted((EXT / "out").rglob("*")):
        if path.is_file():
            files.append((path, "extension/" + path.relative_to(EXT).as_posix()))
    return files


def main() -> None:
    pkg = json.loads((EXT / "package.json").read_text())
    DIST.mkdir(exist_ok=True)
    target = DIST / f"{pkg['name']}.vsix"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("extension.vsixmanifest", manifest(pkg))
        for src, arc in collect():
            z.write(src, arc)
    print(f"wrote {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
