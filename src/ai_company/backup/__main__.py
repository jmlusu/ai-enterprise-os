"""Run the backup bundle tool as ``python -m ai_company.backup``.

Required so the documented entry point (docstring, README and the
``nightly-backup.yml`` workflow) works: ``python -m <package>`` executes
the package's ``__main__`` module, which forwards to :func:`main`.
"""

import sys

from ai_company.backup.backup import main

if __name__ == "__main__":
    sys.exit(main())
