import sys

# `update` loads only what it needs: pip can then replace the packages the rest of the CLI loads (Windows doesn't let
# it replace a package a process uses).
if sys.argv[1:2] == ["update"]:
    from miningcat.interfaces.cli.update_command import main
    main(sys.argv[2:])
else:
    from miningcat.interfaces.cli.main import main
    main()
