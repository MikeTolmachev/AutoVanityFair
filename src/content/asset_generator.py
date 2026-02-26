"""
Vertex AI asset generator for LinkedIn post media.

Uses the google.genai SDK. Supports:
- Gemini models (gemini-*) via generate_content with response_modalities=["IMAGE"]
- Imagen models (imagen-*) via generate_images
- Veo models (veo-*) via generate_videos (async with polling)

Requires: gcloud auth application-default login
"""

import logging
import os
import time

logger = logging.getLogger("openlinkedin.asset_generator")


class AssetGenerator:
    """Generate images and videos using Google Vertex AI (genai SDK)."""

    def __init__(
        self,
        project_id: str,
        location: str = "global",
        imagen_model: str = "gemini-3.1-flash-image-preview",
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

            self._client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location,
            )
            logger.info(
                "GenAI client initialized (project=%s, location=%s)",
                self.project_id,
                self.location,
            )
        return self._client

    def _is_gemini_model(self) -> bool:
        return self.imagen_model.startswith("gemini")

    def generate_image(
        self,
        prompt: str,
        output_dir: str = "data/assets",
        aspect_ratio: str = "1:1",
    ) -> str:
        """Generate an image and save to disk.

        Automatically selects the right API based on model name:
        - gemini-* models use generate_content with response_modalities=["IMAGE"]
        - imagen-* models use generate_images

        Returns the path to the saved PNG file.
        """
        client = self._get_client()
        logger.info("Generating image with %s: %s", self.imagen_model, prompt[:80])

        if self._is_gemini_model():
            image_bytes = self._generate_with_gemini(client, prompt, aspect_ratio)
        else:
            image_bytes = self._generate_with_imagen(client, prompt, aspect_ratio)

        os.makedirs(output_dir, exist_ok=True)
        filename = f"imagen_{int(time.time())}.png"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        logger.info("Image saved to %s (%d bytes)", filepath, len(image_bytes))
        return filepath

    def _generate_with_gemini(self, client, prompt: str, aspect_ratio: str) -> bytes:
        """Use Gemini's generate_content API with IMAGE response modality."""
        from google.genai import types

        response = client.models.generate_content(
            model=self.imagen_model,
            contents=types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            ),
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size="2K",
                    output_mime_type="image/png",
                ),
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                return part.inline_data.data

        raise RuntimeError("No image returned in Gemini response")

    def _generate_with_imagen(self, client, prompt: str, aspect_ratio: str) -> bytes:
        """Use Imagen's generate_images API."""
        from google.genai import types

        response = client.models.generate_images(
            model=self.imagen_model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=aspect_ratio,
                output_mime_type="image/png",
            ),
        )

        if not response.generated_images:
            raise RuntimeError("No image returned in Imagen response")

        return response.generated_images[0].image.image_bytes

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

        operation = client.models.generate_videos(
            model=self.veo_model,
            prompt=prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio=aspect_ratio,
                number_of_videos=1,
                duration_seconds=duration_seconds,
            ),
        )

        # Poll for completion
        while not operation.done:
            time.sleep(10)
            operation = client.operations.get(operation)
            logger.info("Video generation in progress...")

        if not operation.result or not operation.result.generated_videos:
            raise RuntimeError("No video returned in response")

        os.makedirs(output_dir, exist_ok=True)
        filename = f"veo_{int(time.time())}.mp4"
        filepath = os.path.join(output_dir, filename)

        video = operation.result.generated_videos[0]
        client.files.download(file=video.video, download_path=filepath)

        logger.info("Video saved to %s", filepath)
        return filepath
