import subprocess
import tempfile
import os
import platform
from typing import Literal, Dict
from functools import lru_cache

from .logger import trace


DEFAULT_JPEG_QUALITY = 75


class ImageTransformer:
    """이미지 변환을 위한 빌더 클래스"""

    def __init__(self, buffer: bytes):
        self.buffer = buffer
        self.new_width: int = 0
        self.new_format: Literal["jpg", "png"] = "png"
        self.jpeg_options: Dict[str, int] = {"quality": DEFAULT_JPEG_QUALITY}

    def resize(self, width: int) -> 'ImageTransformer':
        """이미지 크기를 조정합니다."""
        self.new_width = width
        return self

    def jpeg(self, options: Dict[str, int]) -> 'ImageTransformer':
        """JPEG 형식으로 변환합니다."""
        self.new_format = "jpg"
        self.jpeg_options = options
        return self

    def png(self) -> 'ImageTransformer':
        """PNG 형식으로 변환합니다."""
        self.new_format = "png"
        return self

    def _quality_to_sips(self, q: int) -> str:
        """JPEG 품질을 sips 포맷으로 변환합니다."""
        if q >= 90:
            return "best"
        if q >= 75:
            return "high"
        if q >= 50:
            return "normal"
        return "low"

    def _to_buffer_with_sips(self) -> bytes:
        """sips를 사용하여 이미지를 변환합니다 (macOS 전용)."""
        temp_dir = tempfile.mkdtemp(prefix="image-")
        input_file = os.path.join(temp_dir, "input")
        output_ext = "jpg" if self.new_format == "jpg" else "png"
        output_file = os.path.join(temp_dir, f"output.{output_ext}")

        try:
            # 입력 파일 작성
            with open(input_file, 'wb') as f:
                f.write(self.buffer)

            # sips 명령 구성
            args = [
                "/usr/bin/sips",
                "-s", "format", "jpeg" if self.new_format == "jpg" else "png"
            ]

            if self.new_format == "jpg":
                args.extend(["-s", "formatOptions", self._quality_to_sips(self.jpeg_options.get("quality", DEFAULT_JPEG_QUALITY))])

            args.extend(["-Z", str(self.new_width)])
            args.extend(["--out", output_file])
            args.append(input_file)

            trace(f"Running sips command: {' '.join(args)}")

            result = subprocess.run(
                args,
                capture_output=True,
                check=True
            )

            with open(output_file, 'rb') as f:
                output_buffer = f.read()

            trace(f"Sips returned buffer of size: {len(output_buffer)}")
            return output_buffer

        finally:
            # 임시 파일 정리
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    def _to_buffer_with_imagemagick(self) -> bytes:
        """ImageMagick을 사용하여 이미지를 변환합니다."""
        cmd = [
            "magick", "-",
            "-resize", f"{self.new_width}x",
            "-quality", str(self.jpeg_options.get("quality", DEFAULT_JPEG_QUALITY)),
            f"{self.new_format}:-"
        ]

        trace(f"Running magick command: {' '.join(cmd)}")

        proc = subprocess.run(
            cmd,
            input=self.buffer,
            capture_output=True,
            check=True
        )

        return proc.stdout

    def to_buffer(self) -> bytes:
        """변환된 이미지를 바이트로 반환합니다."""
        # macOS에서 sips 시도
        if is_sips_installed():
            try:
                return self._to_buffer_with_sips()
            except Exception as e:
                trace(f"Sips failed, falling back to ImageMagick: {e}")

        # ImageMagick 시도
        try:
            return self._to_buffer_with_imagemagick()
        except Exception as e:
            trace(f"ImageMagick failed: {e}")
            raise RuntimeError("Image scaling unavailable (requires Sips or ImageMagick).")


class Image:
    """이미지 처리를 위한 메인 클래스"""

    def __init__(self, buffer: bytes):
        self.buffer = buffer

    @classmethod
    def from_buffer(cls, buffer: bytes) -> 'Image':
        """버퍼로부터 Image 인스턴스를 생성합니다."""
        return cls(buffer)

    def resize(self, width: int) -> ImageTransformer:
        """이미지 크기 조정을 시작합니다."""
        return ImageTransformer(self.buffer).resize(width)

    def jpeg(self, options: Dict[str, int]) -> ImageTransformer:
        """JPEG 변환을 시작합니다."""
        return ImageTransformer(self.buffer).jpeg(options)


def _is_darwin() -> bool:
    """macOS인지 확인합니다."""
    return platform.system() == "Darwin"


@lru_cache(maxsize=1)
def is_sips_installed() -> bool:
    """sips가 설치되어 있는지 확인합니다 (macOS 전용)."""
    if not _is_darwin():
        return False

    try:
        subprocess.run(
            ["/usr/bin/sips", "--version"],
            capture_output=True,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


@lru_cache(maxsize=1)
def is_imagemagick_installed() -> bool:
    """ImageMagick이 설치되어 있는지 확인합니다."""
    try:
        result = subprocess.run(
            ["magick", "--version"],
            capture_output=True,
            text=True,
            check=True
        )

        return any("Version: ImageMagick" in line for line in result.stdout.split("\n"))
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def is_scaling_available() -> bool:
    """이미지 스케일링이 가능한지 확인합니다."""
    return is_imagemagick_installed() or is_sips_installed()
