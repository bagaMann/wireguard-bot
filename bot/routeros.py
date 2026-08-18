import asyncio
import logging

from librouteros import connect

logger = logging.getLogger(__name__)


class RouterOSClient:
    def __init__(self, settings):
        self.settings = settings

    def _connect(self):
        kwargs = {
            "username": self.settings.routeros_username,
            "password": self.settings.routeros_password,
            "host": self.settings.routeros_host,
            "port": self.settings.routeros_port,
        }

        if self.settings.routeros_ssl:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            kwargs["ssl_wrapper"] = ctx.wrap_socket

        return connect(**kwargs)

    def _add_peer_sync(self, public_key, allowed_address, comment, name):
        api = self._connect()
        try:
            path = api.path("/interface/wireguard/peers")
            peer_id = path.add(
                interface=self.settings.routeros_interface,
                **{
                    "public-key": public_key,
                    "allowed-address": allowed_address,
                    "comment": comment,
                    "name": name,
                    "responder": "yes",
                },
            )
            if not peer_id:
                raise RuntimeError("RouterOS did not return a peer ID")
            return peer_id
        finally:
            api.close()

    def _remove_peer_sync(self, peer_id):
        api = self._connect()
        try:
            api.path("/interface/wireguard/peers").remove(peer_id)
        finally:
            api.close()

    def _set_peer_disabled_sync(self, peer_id, disabled: bool):
        api = self._connect()
        try:
            path = api.path("/interface/wireguard/peers")
            path.update(**{
                ".id": peer_id,
                "disabled": disabled,
            })
        finally:
            api.close()

    def _test_sync(self):
        api = self._connect()
        try:
            list(api.path("/interface/wireguard").select("name"))
        finally:
            api.close()

    async def add_peer(self, public_key, allowed_address, comment, name):
        return await asyncio.to_thread(
            self._add_peer_sync,
            public_key,
            allowed_address,
            comment,
            name,
        )

    async def remove_peer(self, peer_id):
        await asyncio.to_thread(self._remove_peer_sync, peer_id)

    async def set_peer_disabled(self, peer_id, disabled: bool):
        await asyncio.to_thread(
            self._set_peer_disabled_sync,
            peer_id,
            disabled,
        )

    async def disable_peer(self, peer_id):
        await self.set_peer_disabled(peer_id, True)

    async def enable_peer(self, peer_id):
        await self.set_peer_disabled(peer_id, False)

    async def test(self):
        await asyncio.to_thread(self._test_sync)
