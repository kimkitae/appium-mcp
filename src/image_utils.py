import subprocess
from typing import Literal, Optional, Dict
from functools import lru_cache


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
    
    def to_buffer(self) -> bytes:
        """변환된 이미지를 바이트로 반환합니다."""
        cmd = [
            "magick", "-", 
            "-resize", f"{self.new_width}x",
            "-quality", str(self.jpeg_options["quality"]),
            f"{self.new_format}:-"
        ]
        
        proc = subprocess.run(
            cmd,
            input=self.buffer,
            capture_output=True,
            check=True
        )
        
        return proc.stdout


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
