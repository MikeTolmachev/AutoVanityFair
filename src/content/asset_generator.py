"""
Vertex AI asset generator for LinkedIn post media.

Supports image generation via Imagen and video generation via Veo.
Uses Application Default Credentials (gcloud auth application-default login).
"""

import logging
import os
import time
from typing import Optional

logger = logging.getLogger("openlinkedin.asset_generator")


class AssetGenerator:
    """Generate images and videos using Google Vertex AI."""

    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        imagen_model: str = "imagen-4.0-generate-001",
        veo_model: str = "veo-3.1-generate-001",
    ):
        self.project_id = project_id
        self.location = location
        self.imagen_model = imagen_model
        self.veo_model = veo_model
        self._initialized = False

    def _init_vertex(self) -> None:
        if self._initialized:
            return
        import vertexai

        vertexai.init(project=self.project_id, location=self.location)
        self._initialized = True
        logger.info(
            "Vertex AI initialized (project=%s, location=%s)",
            self.project_id,
            self.location,
        )

    def generate_image(
        self,
        prompt: str,
        output_dir: str = "data/assets",
        aspect_ratio: str = "1:1",
    ) -> str:
        """Generate an image with Imagen and save to disk.

        Returns the path to the saved PNG file.
        """
        self._init_vertex()
        from vertexai.preview.vision_models import ImageGenerationModel

        model = ImageGenerationModel.from_pretrained(self.imagen_model)
        logger.info("Generating image with %s: %s", self.imagen_model, prompt[:80])

        response = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio=aspect_ratio,
        )

        os.makedirs(output_dir, exist_ok=True)
        filename = f"imagen_{int(time.time())}.png"
        filepath = os.path.join(output_dir, filename)

        response.images[0].save(filepath)
        logger.info("Image saved to %s", filepath)
        return filepath

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
        self._init_vertex()
        from vertexai.preview.vision_models import VideoGenerationModel

        model = VideoGenerationModel.from_pretrained(self.veo_model)
        logger.info("Generating video with %s: %s", self.veo_model, prompt[:80])

        response = model.generate_videos(
            prompt=prompt,
            number_of_videos=1,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
        )

        os.makedirs(output_dir, exist_ok=True)
        filename = f"veo_{int(time.time())}.mp4"
        filepath = os.path.join(output_dir, filename)

        response.videos[0].save(filepath)
        logger.info("Video saved to %s", filepath)
        return filepath
