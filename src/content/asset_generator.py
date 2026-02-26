"""
Vertex AI asset generator for LinkedIn post media.

Uses the google.genai SDK with Gemini models for image generation
and Veo for video generation.
Requires: gcloud auth application-default login
"""

import base64
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("openlinkedin.asset_generator")


class AssetGenerator:
    """Generate images and videos using Google Vertex AI (genai SDK)."""

    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        imagen_model: str = "gemini-3-pro-image-preview",
        veo_model: str = "veo-3.1-generate-001",
    ):
        self.project_id = project_id
        self.location = location
        self.imagen_model = imagen_model
        self.veo_model = veo_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(vertexai=True, project=self.project_id, location=self.location)
            logger.info(
                "GenAI client initialized (project=%s, location=%s)",
                self.project_id,
                self.location,
            )
        return self._client

    def generate_image(
        self,
        prompt: str,
        output_dir: str = "data/assets",
        aspect_ratio: str = "1:1",
    ) -> str:
        """Generate an image with Gemini and save to disk.

        Returns the path to the saved PNG file.
        """
        from google.genai import types

        client = self._get_client()
        logger.info("Generating image with %s: %s", self.imagen_model, prompt[:80])

        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )
        ]

        config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            max_output_tokens=32768,
            response_modalities=["TEXT", "IMAGE"],
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            ],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size="1K",
                output_mime_type="image/png",
            ),
        )

        response = client.models.generate_content(
            model=self.imagen_model,
            contents=contents,
            config=config,
        )

        # Extract the image from the response parts
        os.makedirs(output_dir, exist_ok=True)
        filename = f"imagen_{int(time.time())}.png"
        filepath = os.path.join(output_dir, filename)

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                with open(filepath, "wb") as f:
                    f.write(part.inline_data.data)
                logger.info("Image saved to %s", filepath)
                return filepath

        raise RuntimeError("No image returned in response")

    def generate_video(
        self,
        prompt: str,
        output_dir: str = "data/assets",
        aspect_ratio: str = "16:9",
        duration_seconds: int = 5,
    ) -> str:
        """Generate a video with Veo and save to disk.

        Returns the path to the saved MP4 file.
        """
        from google.genai import types

        client = self._get_client()
        logger.info("Generating video with %s: %s", self.veo_model, prompt[:80])

        config = types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            number_of_videos=1,
            duration_seconds=duration_seconds,
        )

        # Veo generation is async -- poll until done
        operation = client.models.generate_videos(
            model=self.veo_model,
            prompt=prompt,
            config=config,
        )

        # Poll for completion
        import time as _time
        while not operation.done:
            _time.sleep(10)
            operation = client.operations.get(operation)
            logger.info("Video generation in progress...")

        os.makedirs(output_dir, exist_ok=True)
        filename = f"veo_{int(time.time())}.mp4"
        filepath = os.path.join(output_dir, filename)

        video = operation.result.generated_videos[0]
        # Download video from URI
        client.files.download(file=video.video, download_path=filepath)

        logger.info("Video saved to %s", filepath)
        return filepath
