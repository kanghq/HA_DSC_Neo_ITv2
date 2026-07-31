"""Auto-detect config flow for DSC Neo ITv2.

Flow:
  1. ``user``: listener host + port form
  2. ``wait``: start a one-shot listener; wait for a panel to connect;
                  capture its Integration ID; advance once the handshake
                  reaches the OpenSession step
  3. ``confirm``: show captured Integration ID; let user enter (or accept
                  the default) Type 2 access code + optional stored PIN;
                  finalise the entry
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_INTEGRATION_ID,
    CONF_PORT,
    CONF_TYPE1_KEY,
    CONF_TYPE2_KEY,
    CONF_USER_PIN,
    DEFAULT_HOST,
    DEFAULT_INSTALLER_CODE,
    DEFAULT_PORT,
    DEFAULT_TYPE2_KEY,
    DOMAIN,
)
from .dsc_itv2 import itv2_framing, packet, tlink_framing
from .dsc_itv2.messages import decode_open_session

_LOGGER = logging.getLogger(__name__)

# --- Selector factories -----------------------------------------------------

_HOST_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))
_PORT_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=65535, step=1, mode=NumberSelectorMode.BOX)
)
# 32 hex chars; rendered as a password so the key is masked in the UI.
_TYPE2_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
# 8-digit Type-1 access code, also masked.
_TYPE1_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
# User PIN / installer code: digits only, password-masked.
_PIN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _preflight_bind(host: str, port: int) -> str | None:
    """Try to bind ``(host, port)`` momentarily and close it.

    Returns a string error key on failure, or ``None`` on success. This is a
    best-effort check so the user gets a specific message in the ``user`` step
    instead of the generic ``bind_failed`` abort after the wait step.
    """
    try:
        server = await asyncio.start_server(
            lambda r, w: None, host=host, port=port,
        )
    except OSError as exc:
        # WinError 10048 / EADDRINUSE -> port already in use
        # WinError 10049 / EADDRNOTAVAIL -> bind address not assigned to this host
        # WinError 10013 / EACCES -> permission denied (privileged port)
        errno = getattr(exc, "errno", None)
        winerror = getattr(exc, "winerror", None)
        if errno in (48, 98, 10048) or winerror == 10048:
            return "port_in_use"
        if errno in (49, 99, 10049) or winerror == 10049:
            return "host_unavailable"
        if errno in (13, 10013) or winerror == 10013:
            return "bind_denied"
        _LOGGER.warning("Pre-flight bind to %s:%s failed: %s", host, port, exc)
        return "bind_failed"
    try:
        server.close()
        with __import__("contextlib").suppress(Exception):
            await server.wait_closed()
    except Exception:  # pragma: no cover - defensive cleanup
        pass
    return None


def _validate_secrets(
    type2_key: str,
    type1_key: str,
    user_pin: str,
    installer_code: str,
) -> dict[str, str]:
    """Return a dict of field -> error key for any invalid secret values.

    Empty optional fields are allowed; non-empty values are checked for the
    expected shape (hex / digit / length).
    """
    errors: dict[str, str] = {}

    key = (type2_key or "").strip()
    if key:
        if len(key) != 32:
            errors[CONF_TYPE2_KEY] = "invalid_type2_key"
        else:
            try:
                bytes.fromhex(key)
            except ValueError:
                errors[CONF_TYPE2_KEY] = "invalid_type2_key"

    t1 = (type1_key or "").strip()
    if t1 and (len(t1) != 8 or not t1.isdigit()):
        errors[CONF_TYPE1_KEY] = "invalid_type1_key"

    pin = (user_pin or "").strip()
    if pin and (not pin.isdigit() or not 4 <= len(pin) <= 6):
        errors[CONF_USER_PIN] = "invalid_user_pin"

    inst = (installer_code or "").strip()
    if inst and (not inst.isdigit() or not 4 <= len(inst) <= 6):
        errors[CONF_INSTALLER_CODE] = "invalid_installer_code"

    return errors


async def _probe_first_panel(host: str, port: int, timeout: float = 120) -> dict[str, Any]:
    """Bind a one-shot listener; return ``{"integration_id", "encryption_type"}``
    from the first panel that connects. Raises on timeout."""
    fut: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            buf = b""
            while not fut.done():
                chunk = await reader.read(4096)
                if not chunk:
                    return
                buf += chunk
                pkt, buf = tlink_framing.extract_packet(buf)
                if pkt is None:
                    continue
                # Capture integration ID from header
                integration_id = pkt.header.decode("ascii", errors="replace")
                # Try to parse the OpenSession to learn the encryption type
                try:
                    frame = itv2_framing.remove_framing(pkt.payload)
                    inner = packet.parse_packet(frame.packet)
                    os_msg = decode_open_session(inner.body)
                    enc = os_msg.encryption_type
                except Exception:
                    enc = 0
                if not fut.done():
                    fut.set_result({
                        "integration_id": integration_id,
                        "encryption_type": enc,
                    })
                return
        finally:
            with __import__("contextlib").suppress(Exception):
                writer.close()
                await writer.wait_closed()

    server = await asyncio.start_server(handle, host=host, port=port)
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    finally:
        server.close()
        try:
            await server.wait_closed()
        except Exception:  # pragma: no cover
            pass


class DscNeoItV2ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """User-driven config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> DscNeoOptionsFlow:
        return DscNeoOptionsFlow()

    def __init__(self) -> None:
        self._host: str = DEFAULT_HOST
        self._port: int = DEFAULT_PORT
        self._integration_id: str | None = None
        self._encryption_type: int = 2
        self._probe_task: asyncio.Task | None = None
        # When set, the flow is editing an existing entry rather than
        # creating a new one. Populated by async_step_reconfigure.
        self._reconfigure_entry: config_entries.ConfigEntry | None = None
        # When set, the flow was triggered by entry.async_start_reauth.
        self._reauth_entry: config_entries.ConfigEntry | None = None
        self._reauth_reason: str | None = None

    # ---- reconfigure entry-point ----

    async def async_step_reconfigure(
        self, user_input: dict | None = None,
    ) -> FlowResult:
        """Edit host / port / access codes on an existing entry.

        Triggered from the entry's three-dots menu > "Reconfigure".
        We re-use the same step sequence as a fresh install, but the
        final step updates the existing entry in place instead of
        creating a new one.
        """
        entry = self._get_reconfigure_entry()
        self._reconfigure_entry = entry
        # Seed defaults from the existing entry so the form is
        # pre-filled with the current values.
        self._host = entry.data.get(CONF_HOST, DEFAULT_HOST)
        self._port = int(entry.data.get(CONF_PORT, DEFAULT_PORT))
        return await self.async_step_user(user_input)

    # ---- reauth entry-point ----

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any],
    ) -> FlowResult:
        """Triggered by ``entry.async_start_reauth`` when the panel
        rejects our credentials at runtime. Hands off to a simple
        confirm form that re-collects the access codes only.
        """
        self._reauth_entry = self._get_reauth_entry()
        self._reauth_reason = self.context.get("reason") or "auth_failed"
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None,
    ) -> FlowResult:
        """Re-collect access codes and update the entry in place."""
        assert self._reauth_entry is not None
        entry = self._reauth_entry
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_secrets(
                user_input.get(CONF_TYPE2_KEY, ""),
                user_input.get(CONF_TYPE1_KEY, ""),
                user_input.get(CONF_USER_PIN, ""),
                user_input.get(CONF_INSTALLER_CODE, ""),
            )
            if not errors:
                new_data = {
                    **entry.data,
                    CONF_TYPE2_KEY: user_input.get(CONF_TYPE2_KEY, DEFAULT_TYPE2_KEY),
                    CONF_TYPE1_KEY: user_input.get(CONF_TYPE1_KEY, ""),
                    CONF_USER_PIN: user_input.get(CONF_USER_PIN, ""),
                    CONF_INSTALLER_CODE: user_input.get(
                        CONF_INSTALLER_CODE, DEFAULT_INSTALLER_CODE,
                    ),
                }
                return self.async_update_reload_and_abort(
                    entry, data=new_data, reason="reauth_successful",
                )

        defaults = {
            CONF_TYPE2_KEY: entry.data.get(CONF_TYPE2_KEY, DEFAULT_TYPE2_KEY),
            CONF_TYPE1_KEY: entry.data.get(CONF_TYPE1_KEY, ""),
            CONF_USER_PIN: entry.data.get(CONF_USER_PIN, ""),
            CONF_INSTALLER_CODE: entry.data.get(
                CONF_INSTALLER_CODE, DEFAULT_INSTALLER_CODE,
            ),
        }
        schema = vol.Schema({
            vol.Required(CONF_TYPE2_KEY, default=defaults[CONF_TYPE2_KEY]): _TYPE2_SELECTOR,
            vol.Optional(CONF_TYPE1_KEY, default=defaults[CONF_TYPE1_KEY]): _TYPE1_SELECTOR,
            vol.Optional(CONF_USER_PIN, default=defaults[CONF_USER_PIN]): _PIN_SELECTOR,
            vol.Optional(CONF_INSTALLER_CODE, default=defaults[CONF_INSTALLER_CODE]): _PIN_SELECTOR,
        })
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"reason": self._reauth_reason or ""},
        )

    # ---- step 1: listener config ----

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = (user_input.get(CONF_HOST) or DEFAULT_HOST).strip()
            try:
                self._port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            except (TypeError, ValueError):
                errors[CONF_PORT] = "invalid_port"
            else:
                if not 1 <= self._port <= 65535:
                    errors[CONF_PORT] = "invalid_port"
            if not errors:
                # Pre-flight test bind so the user sees a specific error
                # (port already in use, bind address not on this host, etc.)
                # right here instead of getting an opaque ``bind_failed``
                # abort one step later.
                bind_err = await _preflight_bind(self._host, self._port)
                if bind_err == "port_in_use":
                    errors[CONF_PORT] = "port_in_use"
                elif bind_err == "host_unavailable":
                    errors[CONF_HOST] = "host_unavailable"
                elif bind_err == "bind_denied":
                    errors[CONF_PORT] = "bind_denied"
                elif bind_err == "bind_failed":
                    errors["base"] = "bind_failed"
            if not errors:
                return await self.async_step_wait()

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=self._host): _HOST_SELECTOR,
            vol.Required(CONF_PORT, default=self._port): _PORT_SELECTOR,
        })
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors,
        )

    # ---- step 2: wait for panel connection ----

    async def async_step_wait(self, user_input: dict | None = None) -> FlowResult:
        """Bind the listener and wait until a panel connects.

        HA's flow engine is request/response, so we kick off the probe
        in a background task and show a progress form. When the probe
        completes the user submits the form to advance.
        """
        if self._probe_task is None:
            self._probe_task = self.hass.async_create_task(
                _probe_first_panel(self._host, self._port),
                name="dsc-config-probe",
            )

        if not self._probe_task.done():
            # Show a holding form. User clicks "Submit" to re-enter this step.
            return self.async_show_form(
                step_id="wait",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "host": str(self._host),
                    "port": str(self._port),
                },
            )

        # Probe finished: collect result or error
        try:
            info = self._probe_task.result()
        except TimeoutError:
            self._probe_task = None
            return self.async_abort(reason="timeout_no_panel")
        except OSError as exc:
            _LOGGER.error("DSC config probe failed to bind: %s", exc)
            self._probe_task = None
            return self.async_abort(reason="bind_failed")
        except Exception:  # pragma: no cover (defensive)
            _LOGGER.exception("DSC config probe crashed")
            self._probe_task = None
            return self.async_abort(reason="probe_failed")

        self._integration_id = info["integration_id"]
        self._encryption_type = int(info.get("encryption_type") or 2)
        self._probe_task = None
        return await self.async_step_confirm()

    # ---- step 3: confirm + capture access codes ----

    async def async_step_confirm(self, user_input: dict | None = None) -> FlowResult:
        if self._integration_id is None:
            return self.async_abort(reason="no_integration_id")

        # Uniqueness: when creating a new entry, the integration_id
        # mustn't collide with an existing one. When reconfiguring, a
        # match is expected, so just update the entry in place.
        await self.async_set_unique_id(self._integration_id)
        if self._reconfigure_entry is None:
            self._abort_if_unique_id_configured()
        else:
            # If the user pointed the reconfigure flow at a different
            # panel, refuse - they should add a new entry instead.
            existing_id = self._reconfigure_entry.data.get(CONF_INTEGRATION_ID)
            if existing_id and existing_id != self._integration_id:
                return self.async_abort(reason="reconfigure_panel_changed")

        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_HOST: self._host,
                CONF_PORT: self._port,
                CONF_INTEGRATION_ID: self._integration_id,
                CONF_TYPE2_KEY: user_input.get(CONF_TYPE2_KEY, DEFAULT_TYPE2_KEY),
                CONF_TYPE1_KEY: user_input.get(CONF_TYPE1_KEY, ""),
                CONF_USER_PIN: user_input.get(CONF_USER_PIN, ""),
                CONF_INSTALLER_CODE: user_input.get(CONF_INSTALLER_CODE, ""),
            }
            errors = _validate_secrets(
                data[CONF_TYPE2_KEY],
                data[CONF_TYPE1_KEY],
                data[CONF_USER_PIN],
                data[CONF_INSTALLER_CODE],
            )
            if not errors:
                if self._reconfigure_entry is not None:
                    return self.async_update_reload_and_abort(
                        self._reconfigure_entry,
                        data=data,
                        reason="reconfigure_successful",
                    )
                return self.async_create_entry(
                    title=f"DSC Neo {self._integration_id}", data=data,
                )

        # Pre-fill from existing entry data on reconfigure so the user
        # only re-types what they want to change.
        defaults: dict[str, Any] = {
            CONF_TYPE2_KEY: DEFAULT_TYPE2_KEY,
            CONF_TYPE1_KEY: "",
            CONF_USER_PIN: "",
            CONF_INSTALLER_CODE: DEFAULT_INSTALLER_CODE,
        }
        if self._reconfigure_entry is not None:
            for key in defaults:
                defaults[key] = self._reconfigure_entry.data.get(key, defaults[key])

        schema = vol.Schema({
            vol.Required(CONF_TYPE2_KEY, default=defaults[CONF_TYPE2_KEY]): _TYPE2_SELECTOR,
            vol.Optional(CONF_TYPE1_KEY, default=defaults[CONF_TYPE1_KEY]): _TYPE1_SELECTOR,
            vol.Optional(CONF_USER_PIN, default=defaults[CONF_USER_PIN]): _PIN_SELECTOR,
            vol.Optional(CONF_INSTALLER_CODE, default=defaults[CONF_INSTALLER_CODE]): _PIN_SELECTOR,
        })
        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "integration_id": self._integration_id,
                "encryption_type": str(self._encryption_type),
            },
        )


class DscNeoOptionsFlow(config_entries.OptionsFlow):
    """In-place editor for existing config entries.

    Accessed via the gear icon on the integration card. Lets the user
    update keys/codes (e.g. add an installer code after the integration
    was first set up without one) without removing and re-adding.

    ``config_entry`` is provided by the base class; assigning it here
    would raise, because Home Assistant made it a read-only property.
    """

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        current = {**self.config_entry.data}

        if user_input is not None:
            errors = _validate_secrets(
                user_input.get(CONF_TYPE2_KEY, ""),
                user_input.get(CONF_TYPE1_KEY, ""),
                user_input.get(CONF_USER_PIN, ""),
                user_input.get(CONF_INSTALLER_CODE, ""),
            )
            if not errors:
                # Merge user input over existing data and persist on
                # the config entry. HA's options-flow machinery reloads
                # the entry automatically when this handler returns; we
                # must NOT call async_reload() ourselves: doing so
                # races with HA's own reload and raises
                # OperationNotAllowed (entry already in UNLOAD_IN_PROGRESS).
                new_data = {**current, **user_input}
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data,
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema({
            vol.Required(
                CONF_TYPE2_KEY,
                default=current.get(CONF_TYPE2_KEY, DEFAULT_TYPE2_KEY),
            ): _TYPE2_SELECTOR,
            vol.Optional(
                CONF_TYPE1_KEY,
                default=current.get(CONF_TYPE1_KEY, ""),
            ): _TYPE1_SELECTOR,
            vol.Optional(
                CONF_USER_PIN,
                default=current.get(CONF_USER_PIN, ""),
            ): _PIN_SELECTOR,
            vol.Optional(
                CONF_INSTALLER_CODE,
                default=current.get(CONF_INSTALLER_CODE, ""),
            ): _PIN_SELECTOR,
        })
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
