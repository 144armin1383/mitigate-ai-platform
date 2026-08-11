from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from providers.base import AIRequest
from providers.openai.provider import OpenAIProvider


class OpenAIProviderStructuredOutputTests(
    unittest.TestCase
):

    def test_structured_output_is_forwarded_to_responses_api(
        self,
    ) -> None:
        provider = OpenAIProvider()

        fake_client = Mock()

        fake_client.responses.create.return_value = (
            SimpleNamespace(
                output_text=(
                    '{"summary":"ok","files":'
                    '[{"path":"x.txt","content":"hello"}]}'
                ),
                usage=None,
            )
        )

        provider.client = fake_client
        provider.api_key = "test"
        provider.default_model = "gpt-5"

        request = AIRequest(
            prompt="Generate the deliverable.",
            system_prompt="Return structured output.",
            output_schema={
                "name": "mitigate_generated_files",
                "description": "Generation envelope.",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "summary": {
                            "type": "string",
                        },
                        "files": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "path": {
                                        "type": "string",
                                    },
                                    "content": {
                                        "type": "string",
                                    },
                                },
                                "required": [
                                    "path",
                                    "content",
                                ],
                            },
                        },
                    },
                    "required": [
                        "summary",
                        "files",
                    ],
                },
            },
        )

        response = provider.generate(
            request
        )

        self.assertTrue(
            response.success
        )

        kwargs = (
            fake_client.responses.create
            .call_args.kwargs
        )

        self.assertIn(
            "text",
            kwargs,
        )

        output_format = kwargs["text"]["format"]

        self.assertEqual(
            output_format["type"],
            "json_schema",
        )

        self.assertEqual(
            output_format["name"],
            "mitigate_generated_files",
        )

        self.assertTrue(
            output_format["strict"]
        )

        self.assertEqual(
            output_format["schema"],
            request.output_schema["schema"],
        )


if __name__ == "__main__":
    unittest.main()
