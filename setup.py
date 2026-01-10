"""Setup script for Rpi-USB-Cloner."""

from pathlib import Path

from setuptools import find_packages, setup

# Read the version from __version__.py
version_dict = {}
with open("rpi_usb_cloner/__version__.py") as f:
    exec(f.read(), version_dict)

VERSION = version_dict["__version__"]

# Read the long description from README
README = Path("README.md").read_text(encoding="utf-8")

setup(
    name="rpi-usb-cloner",
    version=VERSION,
    author="2wenty2wo",
    description="USB Cloner/Duplicator using a Raspberry Pi Zero with OLED display",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/2wenty2wo/Rpi-USB-Cloner",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.8",
    install_requires=[
        "Pillow>=10.1.0",
        "luma.core>=2.4.2",
        "luma.oled>=3.12.0",
        "RPi.GPIO>=0.7.1",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pytest-mock>=3.10.0",
            "ruff>=0.1.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "rpi-usb-cloner=rpi_usb_cloner.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Systems Administration",
        "Topic :: Utilities",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: POSIX :: Linux",
    ],
    keywords="raspberry-pi usb cloner duplicator backup imaging clonezilla",
    project_urls={
        "Bug Reports": "https://github.com/2wenty2wo/Rpi-USB-Cloner/issues",
        "Source": "https://github.com/2wenty2wo/Rpi-USB-Cloner",
        "Documentation": "https://github.com/2wenty2wo/Rpi-USB-Cloner#readme",
    },
    include_package_data=True,
    package_data={
        "rpi_usb_cloner": [
            "ui/assets/*.webp",
            "ui/assets/*.gif",
            "ui/assets/fonts/*.ttf",
        ],
    },
)
