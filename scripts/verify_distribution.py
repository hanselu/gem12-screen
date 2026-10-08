"""核对待发布的 wheel 和源码包；不访问硬件。"""

from email.parser import BytesParser
from pathlib import Path
import re
import sys
import tarfile
import tomllib
from zipfile import ZipFile


def verify(directory: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    license_text = (root / "LICENSE").read_bytes()
    wheels = list(directory.glob("*.whl"))
    sources = list(directory.glob("*.tar.gz"))
    assert len(wheels) == len(sources) == 1, "应只提供本次版本的一个 wheel 和一个源码包"
    example_images = {f"gem12_screen/assets/example_images/{n:02}.jpg" for n in range(1, 10)}
    required = {"gem12_screen/__init__.py", "gem12_screen/screen.py",
                "gem12_screen/_protocol.py", "gem12_screen/cli.py"} | example_images

    with ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        assert required <= names, "wheel 缺少屏控代码或示例图片"
        assert {n for n in names if n.startswith("gem12_screen/assets/")
                and n.endswith(".jpg")} == example_images, "wheel 图片资源与当前示例不一致"
        for name in example_images:
            assert wheel.read(name) == (root / name).read_bytes(), "wheel 示例图片内容不一致"
        assert not any(n.startswith(("gem12_touch/", "tests/", "docs/", ".tmp/", "reference/", "local_test_images/"))
                       for n in names), "wheel 混入实验代码、测试或本地记录"
        metadata_path = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(wheel.read(metadata_path))
        assert metadata["Name"] == project["name"]
        assert metadata["Version"] == project["version"]
        assert metadata["Requires-Python"] == project["requires-python"]
        assert metadata["License-Expression"] == project["license"] == "0BSD"
        assert metadata.get_all("License-File") == ["LICENSE"]
        license_path = metadata_path.replace("METADATA", "licenses/LICENSE")
        assert wheel.read(license_path) == license_text, "wheel 许可证内容不一致"
        dependencies = {re.match(r"[\w.-]+", item).group().lower()
                        for item in metadata.get_all("Requires-Dist", [])}
        assert dependencies == {"pillow", "pyserial"}, "运行依赖不符合屏控库边界"
        entry_points = wheel.read(metadata_path.replace("METADATA", "entry_points.txt")).decode()
        assert "gem12-screen = gem12_screen.cli:main" in entry_points

    with tarfile.open(sources[0], "r:gz") as source:
        names = {m.name.split("/", 1)[1] for m in source.getmembers() if "/" in m.name}
        assert required <= names, "源码包缺少屏控代码或示例图片"
        assert {n for n in names if n.startswith("gem12_screen/assets/")
                and n.endswith(".jpg")} == example_images, "源码包图片资源与当前示例不一致"
        assert {"README.md", "pyproject.toml", "LICENSE", "tests/test_protocol.py",
                "tests/test_screen.py", "scripts/generate_example_images.py"} <= names
        for name in example_images:
            member = next(m for m in source.getmembers() if m.name.split("/", 1)[-1] == name)
            with source.extractfile(member) as image_file:
                assert image_file.read() == (root / name).read_bytes(), "源码包示例图片内容不一致"
        license_member = next(m for m in source.getmembers() if m.name.split("/", 1)[-1] == "LICENSE")
        with source.extractfile(license_member) as license_file:
            assert license_file.read() == license_text, "源码包许可证内容不一致"
        metadata_member = next(m for m in source.getmembers() if m.name.split("/", 1)[-1] == "PKG-INFO")
        with source.extractfile(metadata_member) as metadata_file:
            metadata = BytesParser().parsebytes(metadata_file.read())
        assert metadata["License-Expression"] == project["license"]
        assert metadata.get_all("License-File") == ["LICENSE"]
        assert not any(n.startswith(("gem12_touch/", ".tmp/", "reference/", "local_test_images/")) for n in names)
        assert "tests/test_touch.py" not in names
        assert not any(n.endswith((".json", ".log", ".pyc")) for n in names), "源码包混入诊断或缓存文件"
    print(f"发行包验证通过：{project['name']} {project['version']}，代码及示例图许可 0BSD，仅屏控，包含 9 张自行绘制的示例图片。")


if __name__ == "__main__":
    verify(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist"))
