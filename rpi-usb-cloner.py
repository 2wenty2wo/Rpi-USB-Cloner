import sys
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(repo_root / "src"))

    from rpi_usb_cloner.main import main as run

    run()


if __name__ == "__main__":
    main()
