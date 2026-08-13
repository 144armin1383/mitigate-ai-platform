from __future__ import annotations

import unittest
from pathlib import Path

from agent.runtime.runtime_gateway import (
    RuntimeGatewayCore,
)


class RuntimeGatewayTests(unittest.TestCase):
    def test_gateway_constructs_with_runtime_paths(
        self,
    ) -> None:
        gateway = RuntimeGatewayCore(
            repository_root=Path(
                "/srv/mitigate/mitigate-ai-platform"
            ),
            runtime_root=Path(
                "/srv/mitigate/external-runtimes"
            ),
        )

        self.assertEqual(
            gateway.openclaw.name,
            "openclaw",
        )

        self.assertEqual(
            gateway.ruflo.name,
            "ruflo",
        )


if __name__ == "__main__":
    unittest.main()
