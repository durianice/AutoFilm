from typing import Any, Literal, overload
from pathlib import Path
from os import makedirs
from asyncio import TaskGroup, to_thread, get_event_loop
from collections.abc import Coroutine
from tempfile import TemporaryDirectory
from shutil import copy
from atexit import register

from httpx import AsyncClient, Client, Response, TimeoutException
from aiofile import async_open

from app.core import settings, logger
from app.utils.url import URLUtils
from app.utils.retry import Retry

loop = get_event_loop()


class HTTPClient:
    """
    HTTP 客户端类
    """

    # 最小流式下载文件大小，128MB
    MINI_STREAM_SIZE: int = 128 * 1024 * 1024
    # 默认请求头
    HEADERS: dict[str, str] = {
        "User-Agent": f"AutoFilm/{settings.APP_VERSION}",
        "Accept": "application/json",
    }

    def __init__(self):
        """
        初始化 HTTP 客户端
        """

        self.__new_async_client()
        self.__new_sync_client()
        register(loop.run_until_complete, self.async_close())
        # register(print, "HTTP 客户端已关闭")
        # self.request()

    def __new_sync_client(self):
        """
        创建新的同步 HTTP 客户端
        """
        self.__sync_client = Client(http2=True, follow_redirects=True, timeout=10)

    def __new_async_client(self):
        """
        创建新的异步 HTTP 客户端
        """
        self.__async_client = AsyncClient(http2=True, follow_redirects=True, timeout=10)

    def close_sync_client(self):
        """
        关闭同步 HTTP 客户端
        """
        if self.__sync_client:
            self.__sync_client.close()

    async def close_async_client(self):
        """
        关闭异步 HTTP 客户端
        """
        if self.__async_client:
            await self.__async_client.aclose()

    def sync_close(self) -> None:
        """
        同步关闭所有客户端
        """
        self.close_sync_client()
        loop.run_until_complete(self.close_async_client())

    async def async_close(self) -> None:
        """
        异步关闭所有客户端
        """
        self.close_sync_client()
        await self.close_async_client()

    @Retry.sync_retry(TimeoutException, tries=3, delay=1, backoff=2, logger=logger)
    def _sync_request(self, method: str, url: str, **kwargs) -> Response:
        """
        发起同步 HTTP 请求
        """
        try:
            return self.__sync_client.request(method, url, **kwargs)
        except TimeoutException:
            self.close_sync_client()
            self.__new_sync_client()
            raise TimeoutException

    @Retry.async_retry(TimeoutException, tries=3, delay=1, backoff=2, logger=logger)
    def _async_request(
        self, method: str, url: str, **kwargs
    ) -> Coroutine[Any, Any, Response]:
        """
        发起异步 HTTP 请求
        """
        try:
            return self.__async_client.request(method, url, **kwargs)
        except TimeoutException:
            self.close_async_client()
            self.__new_async_client()
            raise TimeoutException

    @overload
    def request(
        self, method: str, url: str, *, sync: Literal[True], **kwargs
    ) -> Response: ...

    @overload
    def request(
        self, method: str, url: str, *, sync: Literal[False] = False, **kwargs
    ) -> Coroutine[Any, Any, Response]: ...

    def request(
        self,
        method: str,
        url: str,
        *,
        sync: Literal[True, False] = False,
        **kwargs,
    ) -> Response | Coroutine[Any, Any, Response]:
        """
        发起 HTTP 请求

        :param method: HTTP 方法，如 get, post, put 等
        :param url: 请求的 URL
        :param sync: 是否使用同步请求方式，默认为 False
        :param kwargs: 其他请求参数，如 headers, cookies 等
        :return: HTTP 响应对象
        """
        headers = kwargs.get("headers", self.HEADERS)
        kwargs["headers"] = headers
        if sync:
            return self._sync_request(method, url, **kwargs)
        else:
            return self._async_request(method, url, **kwargs)

    @overload
    def head(self, url: str, *, sync: Literal[True], **kwargs) -> Response: ...

    @overload
    def head(
        self, url: str, *, sync: Literal[False], **kwargs
    ) -> Coroutine[Any, Any, Response]: ...

    async def head(
        self,
        url: str,
        *,
        sync: Literal[True, False] = False,
        params: dict = {},
        **kwargs,
    ) -> Response | Coroutine[Any, Any, Response]:
        """
        发送 HEAD 请求

        :param url: 请求的 URL
        :param sync: 是否使用同步请求方式，默认为 False
        :param params: 请求的查询参数
        :param kwargs: 其他请求参数，如 headers, cookies 等
        :return: HTTP 响应对象
        """
        # 合并所有参数到一个字典中
        request_kwargs = {'params': params}
        request_kwargs.update(kwargs)
        resp = await self.request("head", url, sync=False, **request_kwargs)
        return resp

    @overload
    def get(self, url: str, *, sync: Literal[True], **kwargs) -> Response: ...

    @overload
    def get(
        self, url: str, *, sync: Literal[False], **kwargs
    ) -> Coroutine[Any, Any, Response]: ...

    def get(
        self,
        url: str,
        *,
        sync: Literal[True, False] = False,
        params: dict = {},
        **kwargs,
    ) -> Response | Coroutine[Any, Any, Response]:
        """
        发送 GET 请求

        :param url: 请求的 URL
        :param sync: 是否使用同步请求方式，默认为 False
        :param params: 请求的查询参数
        :param kwargs: 其他请求参数，如 headers, cookies 等
        :return: HTTP 响应对象
        """
        return self.request("get", url, sync=sync, params=params, **kwargs)

    @overload
    def post(self, url: str, *, sync: Literal[True], **kwargs) -> Response: ...

    @overload
    def post(
        self, url: str, *, sync: Literal[False], **kwargs
    ) -> Coroutine[Any, Any, Response]: ...

    def post(
        self,
        url: str,
        *,
        sync: Literal[True, False] = False,
        data: Any = None,
        json: dict = {},
        **kwargs,
    ) -> Response | Coroutine[Any, Any, Response]:
        """
        发送 POST 请求

        :param url: 请求的 URL
        :param sync: 是否使用同步请求方式，默认为 False
        :param data: 请求的数据
        :param json: 请求的 JSON 数据
        :param kwargs: 其他请求参数，如 headers, cookies 等
        :return: HTTP 响应对象
        """
        return self.request("post", url, sync=sync, data=data, json=json, **kwargs)

    @overload
    def put(self, url: str, *, sync: Literal[True], **kwargs) -> Response: ...

    @overload
    def put(
        self, url: str, *, sync: Literal[False], **kwargs
    ) -> Coroutine[Any, Any, Response]: ...

    def put(
        self,
        url: str,
        *,
        sync: Literal[True, False] = False,
        data: Any = None,
        json: dict = {},
        **kwargs,
    ) -> Response | Coroutine[Any, Any, Response]:
        """
        发送 PUT 请求

        :param url: 请求的 URL
        :param sync: 是否使用同步请求方式，默认为 False
        :param data: 请求的数据
        :param json: 请求的 JSON 数据
        :param kwargs: 其他请求参数，如 headers, cookies 等
        :return: HTTP 响应对象
        """
        return self.request("put", url, sync=sync, data=data, json=json**kwargs)

    async def download(
        self,
        url: str,
        file_path: Path,
        params: dict | None = None,
        chunk_num: int = 5,
        **kwargs,
    ) -> None:
        """
        下载文件！！！仅支持异步下载！！！

        :param url: 文件的 URL
        :param file_path: 文件保存路径
        :param params: 请求参数
        :param kwargs: 其他请求参数，如 headers, cookies 等
        """
        if params is None:
            params = {}

        # 合并所有参数到一个字典中
        request_kwargs = {'params': params}
        request_kwargs.update(kwargs)
        resp = await self.head(url, sync=False, **request_kwargs)
        print(resp.headers)

        file_size = int(resp.headers.get("Content-Length", -1))

        with TemporaryDirectory(prefix="AutoFilm_") as temp_dir:  # 创建临时目录
            temp_file = Path(temp_dir) / file_path.name
            if not temp_file.exists():
                temp_file.touch()
            if file_size == -1:
                logger.debug(f"{file_path.name} 文件大小未知，直接下载")
                await self.__download_chunk(url, temp_file, 0, 0, **kwargs)
            else:
                async with TaskGroup() as tg:
                    try:
                        logger.debug(
                            f"开始分片下载文件：{file_path.name}，分片数:{chunk_num}"
                        )
                        for start, end in self.caculate_divisional_range(
                            file_size, chunk_num=chunk_num
                        ):
                            tg.create_task(
                                self.__download_chunk(url, temp_file, start, end, **kwargs)
                            )
                        copy(temp_file, file_path)
                    except Exception as e:
                        logger.error(f"分片下载处理失败 {str(e)}")
                        raise

    async def __download_chunk(
        self,
        url: str,
        file_path: Path,
        start: int,
        end: int,
        iter_chunked_size: int = 64 * 1024,
        **kwargs,
    ):
        """
        下载文件的分片

        :param url: 文件的 URL
        :param file_path: 文件保存路径
        :param start: 分片的开始位置
        :param end: 分片的结束位置
        :param iter_chunked_size: 下载的块大小（下载完成后再写入硬盘），默认为 64KB
        :param kwargs: 其他请求参数，如 headers, cookies, proxies 等
        """

        await to_thread(makedirs, file_path.parent, exist_ok=True)

        if start != 0 and end != 0:
            headers = kwargs.get("headers", {})
            headers["Range"] = f"bytes={start}-{end}"
            kwargs["headers"] = headers

        resp = await self.get(url, sync=False, **kwargs)
        async with async_open(file_path, "ab") as file:
            file.seek(start)
            async for chunk in resp.aiter_bytes(iter_chunked_size):
                await file.write(chunk)

    @staticmethod
    def caculate_divisional_range(
        file_size: int,
        chunk_num: int,
    ) -> list[tuple[int, int]]:
        """
        计算文件的分片范围

        :param file_size: 文件大小
        :param chunk_num: 分片数
        :return: 分片范围
        """
        if file_size < HTTPClient.MINI_STREAM_SIZE or chunk_num <= 1:
            return [(0, file_size - 1)]

        step = file_size // chunk_num  # 计算每个分片的基本大小
        remainder = file_size % chunk_num  # 计算剩余的字节数

        chunks = []
        start = 0

        for i in range(chunk_num):
            # 如果有剩余字节，分配一个给当前分片
            end = start + step + (1 if i < remainder else 0) - 1
            chunks.append((start, end))
            start = end + 1

        return chunks


class RequestUtils:
    """
    HTTP 请求工具类
    支持同步和异步请求
    """

    __clients: dict[str, HTTPClient] = {}

    @classmethod
    def close(cls):
        """
        关闭所有 HTTP 客户端
        """
        for client in cls.__clients.values():
            client.sync_close()

    @classmethod
    def __get_client(cls, url: str) -> HTTPClient:
        """
        获取 HTTP 客户端

        :param url: 请求的 URL
        :return: HTTP 客户端
        """

        _, domain, port = URLUtils.get_resolve_url(url)
        key = f"{domain}:{port}"
        if key not in cls.__clients:
            cls.__clients[key] = HTTPClient()
        return cls.__clients[key]

    @overload
    @classmethod
    def request(
        cls, method: str, url: str, sync: Literal[True], **kwargs
    ) -> Response: ...

    @overload
    @classmethod
    def request(
        cls, method: str, url: str, sync: Literal[False] = False, **kwargs
    ) -> Coroutine[Any, Any, Response]: ...

    @classmethod
    def request(
        cls, method: str, url: str, sync: Literal[True, False] = False, **kwargs
    ) -> Response | Coroutine[Any, Any, Response]:
        """
        发起 HTTP 请求
        """
        client = cls.__get_client(url)
        return client.request(method, url, sync=sync, **kwargs)

    @overload
    @classmethod
    def head(cls, url: str, sync: Literal[True], **kwargs) -> Response: ...

    @overload
    @classmethod
    def head(
        cls, url: str, sync: Literal[False] = False, **kwargs
    ) -> Coroutine[Any, Any, Response]: ...

    @classmethod
    def head(
        cls,
        url: str,
        *,
        sync: Literal[True, False] = False,
        params: dict = {},
        **kwargs,
    ) -> Response | Coroutine[Any, Any, Response]:
        """
        发送 HEAD 请求

        :param url: 请求的 URL
        :param sync: 是否使用同步请求方式，默认为 False
        :param params: 请求的查询参数
        :param kwargs: 其他请求参数，如 headers, cookies 等
        :return: HTTP 响应对象
        """
        return cls.request("head", url, sync=sync, params=params, **kwargs)

    @overload
    @classmethod
    def get(cls, url: str, *, sync: Literal[True], **kwargs) -> Response: ...

    @overload
    @classmethod
    def get(
        cls, url: str, *, sync: Literal[False] = False, **kwargs
    ) -> Coroutine[Any, Any, Response]: ...

    @classmethod
    def get(
        cls,
        url: str,
        *,
        sync: Literal[True, False] = False,
        params: dict = {},
        **kwargs,
    ) -> Response | Coroutine[Any, Any, Response]:
        """
        发送 GET 请求

        :param url: 请求的 URL
        :param params: 请求的查询参数
        :param kwargs: 其他请求参数，如 headers, cookies 等
        :return: HTTP 响应对象
        """
        return cls.request("get", url, sync=sync, params=params, **kwargs)

    @overload
    @classmethod
    def post(cls, url: str, *, sync: Literal[True], **kwargs) -> Response: ...

    @overload
    @classmethod
    def post(
        cls,
        url: str,
        *,
        sync: Literal[False] = False,
        data: Any = None,
        json: dict = {},
        **kwargs,
    ) -> Coroutine[Any, Any, Response]: ...

    @classmethod
    def post(
        cls,
        url: str,
        *,
        sync: Literal[True, False] = False,
        data: Any = None,
        json: dict = {},
        **kwargs,
    ) -> Response | Coroutine[Any, Any, Response]:
        """
        发送 POST 请求

        :param url: 请求的 URL
        :param data: 请求的数据
        :param json: 请求的 JSON 数据
        :param kwargs: 其他请求参数，如 headers, cookies 等
        :return: HTTP 响应对象
        """
        return cls.request("post", url, sync=sync, data=data, json=json, **kwargs)

    @overload
    @classmethod
    def put(cls, url: str, *, sync: Literal[True], **kwargs) -> Response: ...

    @overload
    @classmethod
    def put(
        cls,
        url: str,
        *,
        sync: Literal[False] = False,
        data: Any = None,
        **kwargs,
    ) -> Coroutine[Any, Any, Response]: ...

    @classmethod
    def put(
        cls, url: str, *, sync: Literal[True, False] = False, data: Any = None, **kwargs
    ) -> Response | Coroutine[Any, Any, Response]:
        """
        发送 PUT 请求

        :param key: 客户端的键
        :param url: 请求的 URL
        :param data: 请求的数据
        :param kwargs: 其他请求参数，如 headers, cookies 等
        :return: HTTP 响应对象
        """
        return cls.request("put", url, sync=sync, data=data, **kwargs)

    @classmethod
    async def download(
        cls,
        url: str,
        file_path: Path,
        params: dict | None = None,
        **kwargs,
    ) -> None:
        """
        下载文件！！！仅支持异步下载！！！

        :param url: 文件的 URL
        :param file_path: 文件保存路径
        :param params: 请求参数
        :param kwargs: 其他请求参数，如 headers, cookies 等
        """
        if params is None:
            params = {}
        try:
            client = cls.__get_client(url)
            await client.download(url, file_path, params=params, **kwargs)
        except Exception as e:
            logger.error(f"下载失败 {str(e)}")
            raise


# 退出时关闭所有客户端
register(RequestUtils.close)
