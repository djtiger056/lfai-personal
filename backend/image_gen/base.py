from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class BaseImageProvider(ABC):
    """图像生成提供商基础接口"""
    
    @abstractmethod
    async def generate(self, prompt: str) -> Optional[bytes]:
        """生成图像
        
        Args:
            prompt: 图像生成提示词
            
        Returns:
            图像二进制数据，失败返回None
        """
        pass

    async def generate_with_images(self, prompt: str, images: List[str]) -> Optional[bytes]:
        """图生图：基于参考图片和提示词生成图像
        
        默认实现回退到文生图，子类可覆盖以提供图生图能力。
        
        Args:
            prompt: 图像生成提示词
            images: 参考图片列表，支持 HTTP/HTTPS URL 或 Base64 Data URL 格式
            
        Returns:
            图像二进制数据，失败返回None
        """
        return await self.generate(prompt)
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """测试连接
        
        Returns:
            连接是否成功
        """
        pass