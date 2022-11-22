import asyncio
import json
import logging
from contextlib import asynccontextmanager
from functools import partial
from http.client import HTTPException

from . import DiscordWebhook

logger = logging.getLogger(__name__)

try:
    import httpx  # noqa
except ImportError:  # pragma: nocover
    # Async is an optional dependency so don't raise
    # an exception unless the AsyncDiscordWebhook is used.
    pass


class AsyncDiscordWebhook(DiscordWebhook):
    """
    Async version of DiscordWebhook.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            import httpx  # noqa
        except ImportError:  # pragma: nocover
            raise ImportError(
                "You're attempting to use the async version of discord-webhooks but"
                " didn't install it using `pip install discord-webhook[async]`."
            ) from None

    @property
    @asynccontextmanager
    async def http_client(self):
        """
        A property that returns a httpx.AsyncClient instance that is used for a 'with' statement.
        Example:
            async with self.http_client as client:
                client.post(url, data=data)
        It will automatically close the client when the context is exited.
        :return: httpx.AsyncClient
        """
        client = httpx.AsyncClient(proxies=self.proxies)
        yield client
        await client.aclose()

    async def api_post_request(self):
        async with self.http_client as client:  # type: httpx.AsyncClient
            if bool(self.files) is False:
                response = await client.post(
                    self.url,
                    json=self.json,
                    params={'wait': True},
                    timeout=self.timeout,
                )
            else:
                self.files["payload_json"] = (
                    None,
                    json.dumps(self.json).encode('utf-8'),
                )
                response = await client.post(
                    self.url, files=self.files, timeout=self.timeout
                )
        return response

   
    async def execute(self, remove_embeds=False, remove_files=False):
        """
        executes the Webhook
        :param remove_embeds: if set to True, calls `self.remove_embeds()` to empty `self.embeds` after webhook is executed
        :param remove_files: if set to True, calls `self.remove_files()` to empty `self.files` after webhook is executed
        :return: Webhook response
        """
        webhook_urls = self.url if isinstance(self.url, list) else [self.url]
        urls_len = len(webhook_urls)
        responses = []
        for i, url in enumerate(webhook_urls):
            response = await self.api_post_request(url)
            if response.status_code in [200, 204]:
                logger.debug(
                    "[{index}/{length}] Webhook executed".format(
                        index=i + 1, length=urls_len
                    )
                )
            elif response.status_code == 429 and self.rate_limit_retry:
                _current = 0
                while (
                    response.status_code == 429
                    and _current < self.rate_limit_max_retries
                ):
                    _current = _current + 1
                    if (
                        self.rate_limit_max_sleep > 0
                        and not await self.get_wait_time(response)
                        < self.rate_limit_max_sleep
                    ):
                        break
                    await self.handle_rate_limit(response)
                    response = await self.api_post_request(url)
                    if response.status_code in [200, 204]:
                        logger.debug(
                            "[{index}/{length}] Webhook executed".format(
                                index=i + 1, length=urls_len
                            )
                        )
                        break
            else:
                logger.error(
                    "[{index}/{length}] Webhook status code {status_code}: {content}".format(
                        index=i + 1,
                        length=urls_len,
                        status_code=response.status_code,
                        content=response.content.decode("utf-8"),
                    )
                )
            )
        if remove_embeds:
            self.remove_embeds()
        if remove_files:
            self.remove_files()
        if webhook_id := json.loads(response.content.decode("utf-8")).get('id'):
            self.id = webhook_id
        return response

    async def edit(self, sent_message_id):
        """
        edits the webhook passed as a response
        :param sent_message_id: message_id
        :return: Another webhook response
        """
        sent_message_id = [sent_message_id]
        webhook_len = len(sent_message_id)
        responses = []
        async with self.http_client as client:  # type: httpx.AsyncClient
            for i, message_id in enumerate(sent_message_id):
                url = self.url.split("?")[0] + "/messages/" + str(message_id)
                if bool(self.files) is False:
                    patch_kwargs = {
                        "json": self.json,
                        "params": {"wait": True},
                        "timeout": self.timeout,
                    }
                else:
                    self.files["payload_json"] = (
                        None,
                        json.dumps(self.json).encode("utf-8"),
                    )
                    patch_kwargs = {
                        "files": self.files,
                        "timeout": self.timeout,
                    }
                response = await client.patch(url, **patch_kwargs)
                if response.status_code in [200, 204]:
                    logger.debug(
                        "[{index}/{length}] Webhook edited".format(
                            index=i + 1,
                            length=webhook_len,
                        )
                    )
                elif response.status_code == 429 and self.rate_limit_retry:
                    _current = 0
                    while (
                        response.status_code == 429
                        and _current < self.rate_limit_max_retries
                    ):
                        _current = _current + 1
                        if (
                            self.rate_limit_max_sleep > 0
                            and not await self.get_wait_time(response)
                            < self.rate_limit_max_sleep
                        ):
                            break
                        await self.handle_rate_limit(response)
                        response = await client.patch(url, **patch_kwargs)
                        if response.status_code in [200, 204]:
                            logger.debug(
                                "[{index}/{length}] Webhook edited".format(
                                    index=i + 1,
                                    length=webhook_len,
                                )
                            )
                            break
                else:
                    logger.error(
                        "[{index}/{length}] Webhook status code {status_code}: {content}".format(
                            index=i + 1,
                            length=webhook_len,
                            status_code=response.status_code,
                            content=response.content.decode("utf-8"),
                        )
                    )
                )
            return response

    async def delete(self, sent_message_ids=[]):
        """
        deletes the webhook passed as a response
        :param sent_message_ids: message ids
        :return: Response
        """
        webhook_len = len(sent_message_ids)
        responses = []
        async with self.http_client as client:  # type: httpx.AsyncClient
            for i, message_id in enumerate(sent_message_ids):
                response = await client.delete(
                    self.url.split("?")[0] + "/messages/" + str(message_id),
                    timeout=self.timeout,
                )
                if response.status_code in [200, 204]:
                    logger.debug(
                        "[{index}/{length}] Webhook deleted".format(
                            index=i + 1,
                            length=webhook_len,
                        )
                    )
                else:
                    logger.error(
                        "[{index}/{length}] Webhook status code {status_code}: {content}".format(
                            index=i + 1,
                            length=webhook_len,
                            status_code=response.status_code,
                            content=response.content.decode("utf-8"),
                        )
                    )
                responses.append(response)
        return responses[0] if len(responses) == 1 else responses

    async def get_wait_time(self, response) -> float:
        errors = response.json()
        if not response.headers.get('Via'):
                raise HTTPException(errors)
        return (int(errors["retry_after"]) / 1000) + 0.15

    async def handle_rate_limit(self, response):
        """
        handles the rate limit
        :param response: Response
        :return: Response
        """
        wh_sleep = await self.get_wait_time(response)
        logger.error(
            "Webhook rate limited: sleeping for {wh_sleep} "
            "seconds... {identifier}".format(
                wh_sleep=wh_sleep, identifier=self.webhook_identifier
            )
        )
        await asyncio.sleep(wh_sleep)
