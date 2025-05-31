from dataclasses import dataclass
from typing import BinaryIO
import struct


@dataclass
class PngDimensions:
    """PNG 이미지의 크기 정보"""
    width: int
    height: int


class PNG:
    """PNG 이미지 처리 클래스"""
    
    def __init__(self, buffer: bytes):
        """
        Args:
            buffer: PNG 이미지의 바이트 데이터
        """
        self.buffer = buffer
    
    def get_dimensions(self) -> PngDimensions:
        """PNG 이미지의 너비와 높이를 반환합니다."""
        # PNG 시그니처 확인
        png_signature = bytes([137, 80, 78, 71, 13, 10, 26, 10])
        
        if self.buffer[:8] != png_signature:
            raise ValueError("유효한 PNG 파일이 아닙니다")
        
        # IHDR 청크에서 너비와 높이 읽기
        # 너비는 16번째 바이트부터 4바이트 (big-endian)
        # 높이는 20번째 바이트부터 4바이트 (big-endian)
        width = struct.unpack('>I', self.buffer[16:20])[0]
        height = struct.unpack('>I', self.buffer[20:24])[0]
        
        return PngDimensions(width=width, height=height) 