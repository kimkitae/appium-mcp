import os
import platform
import shutil
import subprocess
import tempfile
from functools import lru_cache
from typing import Dict, Literal, Optional


DEFAULT_JPEG_QUALITY = 75


class ImageTransformer:
    """이미지 변환을 위한 빌더 클래스"""

    def __init__(self, buffer: bytes):
        self.buffer = buffer
        self.new_width: Optional[int] = None
        self.new_format: Literal["jpg", "png"] = "png"
        self.jpeg_options: Dict[str, int] = {"quality": DEFAULT_JPEG_QUALITY}

    def resize(self, width: int) -> "ImageTransformer":
        """이미지 크기를 조정합니다."""
        self.new_width = width if width > 0 else None
        return self

    def jpeg(self, options: Dict[str, int]) -> "ImageTransformer":
        """JPEG 형식으로 변환합니다."""
        self.new_format = "jpg"
        self.jpeg_options = options
        return self

    def png(self) -> "ImageTransformer":
        """PNG 형식으로 변환합니다."""
        self.new_format = "png"
        return self

    def to_buffer(self) -> bytes:
        """변환된 이미지를 바이트로 반환합니다."""
        if is_sips_installed():
            try:
                return self._to_buffer_with_sips()
            except Exception:
                pass

        if is_imagemagick_installed():
            return self._to_buffer_with_imagemagick()

        raise RuntimeError("이미지 압축 도구를 찾을 수 없습니다. (sips 또는 ImageMagick 필요)")

    def _quality_to_sips(self, quality: int) -> str:
        if quality >= 90:
            return "best"
        if quality >= 75:
            return "high"
        if quality >= 50:
            return "normal"
        return "low"

    def _to_buffer_with_sips(self) -> bytes:
        temp_dir = tempfile.mkdtemp(prefix="image-")
        input_file = os.path.join(temp_dir, "input")
        output_ext = "jpg" if self.new_format == "jpg" else "png"
        output_file = os.path.join(temp_dir, f"output.{output_ext}")

        try:
            with open(input_file, "wb") as f:
                f.write(self.buffer)

            fmt = "jpeg" if self.new_format == "jpg" else "png"
            cmd = ["/usr/bin/sips", "-s", "format", fmt]
            if self.new_format == "jpg":
                quality = int(self.jpeg_options.get("quality", DEFAULT_JPEG_QUALITY))
                cmd.extend(["-s", "formatOptions", self._quality_to_sips(quality)])

            if self.new_width:
                cmd.extend(["-Z", str(self.new_width)])

            cmd.extend(["--out", output_file, input_file])
            subprocess.run(cmd, capture_output=True, check=True)

            with open(output_file, "rb") as f:
                return f.read()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _to_buffer_with_imagemagick(self) -> bytes:
        cmd = ["magick", "-"]
        if self.new_width:
            cmd.extend(["-resize", f"{self.new_width}x"])
        if self.new_format == "jpg":
            quality = int(self.jpeg_options.get("quality", DEFAULT_JPEG_QUALITY))
            cmd.extend(["-quality", str(quality)])
        cmd.append(f"{self.new_format}:-")
        proc = subprocess.run(cmd, input=self.buffer, capture_output=True, check=True)
        return proc.stdout


class Image:
    """이미지 처리를 위한 메인 클래스"""

    def __init__(self, buffer: bytes):
        self.buffer = buffer

    @classmethod
    def from_buffer(cls, buffer: bytes) -> "Image":
        """버퍼로부터 Image 인스턴스를 생성합니다."""
        return cls(buffer)

    def resize(self, width: int) -> ImageTransformer:
        """이미지 크기 조정을 시작합니다."""
        return ImageTransformer(self.buffer).resize(width)

    def jpeg(self, options: Dict[str, int]) -> ImageTransformer:
        """JPEG 변환을 시작합니다."""
        return ImageTransformer(self.buffer).jpeg(options)


@lru_cache(maxsize=1)
def is_sips_installed() -> bool:
    """sips가 설치되어 있는지 확인합니다."""
    if platform.system() != "Darwin":
        return False
    try:
        subprocess.run(["/usr/bin/sips", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def is_imagemagick_installed() -> bool:
    """ImageMagick이 설치되어 있는지 확인합니다."""
    try:
        result = subprocess.run(
            ["magick", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        return any("Version: ImageMagick" in line for line in result.stdout.split("\n"))
    except Exception:
        return False


def is_scaling_available() -> bool:
    """이미지 리사이즈/압축 가능 여부를 확인합니다."""
    return is_sips_installed() or is_imagemagick_installed()
