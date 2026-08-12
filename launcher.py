import sys


if "--studio-manim-cli" in sys.argv:
    sys.argv.remove("--studio-manim-cli")
    from manim.__main__ import main
else:
    from manim_media_studio.app import main


if __name__ == "__main__":
    raise SystemExit(main())
