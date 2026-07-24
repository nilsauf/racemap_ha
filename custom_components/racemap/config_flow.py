"""Config and options flow for RaceMap."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import RaceMapApiClient
from .const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_UPDATE_INTERVAL,
)
from .coordinator import RaceMapConfigEntry, RaceMapDataUpdateCoordinator
from .exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapError,
    RaceMapEventNotFoundError,
    RaceMapRateLimitError,
)
from .models import RaceData

TOKEN_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD)
)


async def _validate(
    hass: Any, token: str, event_id: str
) -> tuple[RaceData | None, str | None]:
    """Validate credentials; return (data, error_key)."""
    session = async_get_clientsession(hass)
    client = RaceMapApiClient(session, token, event_id)
    try:
        return await client.async_get_current(), None
    except RaceMapAuthError:
        return None, "invalid_auth"
    except RaceMapEventNotFoundError:
        return None, "event_not_found"
    except (RaceMapConnectionError, RaceMapRateLimitError):
        return None, "cannot_connect"
    except RaceMapError:
        return None, "cannot_connect"
    except Exception:  # noqa: BLE001
        LOGGER.exception("Unexpected error validating RaceMap connection")
        return None, "unknown"


class RaceMapConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RaceMap."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data, error = await _validate(
                self.hass, user_input[CONF_TOKEN], user_input[CONF_EVENT_ID]
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(user_input[CONF_EVENT_ID])
                self._abort_if_unique_id_configured()
                title = (data.event.name if data else None) or user_input[
                    CONF_EVENT_ID
                ]
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
                    vol.Required(CONF_EVENT_ID): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth on auth failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth with a new token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            _data, error = await _validate(
                self.hass, user_input[CONF_TOKEN], entry.data[CONF_EVENT_ID]
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(entry.data[CONF_EVENT_ID])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of token/event id."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            _data, error = await _validate(
                self.hass, user_input[CONF_TOKEN], user_input[CONF_EVENT_ID]
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(user_input[CONF_EVENT_ID])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TOKEN, default=entry.data[CONF_TOKEN]
                    ): TOKEN_SELECTOR,
                    vol.Required(
                        CONF_EVENT_ID, default=entry.data[CONF_EVENT_ID]
                    ): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: RaceMapConfigEntry,
    ) -> RaceMapOptionsFlow:
        """Return the options flow."""
        return RaceMapOptionsFlow()


class RaceMapOptionsFlow(OptionsFlowWithReload):
    """Handle RaceMap options (refresh interval + participants)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            self._cleanup_stale_devices(
                user_input.get(CONF_PARTICIPANTS, []),
            )
            return self.async_create_entry(data=user_input)

        coordinator: RaceMapDataUpdateCoordinator | None = getattr(
            self.config_entry, "runtime_data", None
        )
        options: list[SelectOptionDict] = []
        if coordinator is not None and coordinator.data is not None:
            options = [
                SelectOptionDict(
                    value=p.id,
                    label=f"{p.display_name} (#{p.start_number})"
                    if p.start_number
                    else p.display_name,
                )
                for p in coordinator.data.participants
            ]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL,
                        max=3600,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional(CONF_PARTICIPANTS, default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                        custom_value=True,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, self.config_entry.options
            ),
        )

    def _cleanup_stale_devices(
        self, participant_ids: list[str],
    ) -> None:
        """Remove this entry's participant devices absent from submitted options."""
        event_id = self.config_entry.data[CONF_EVENT_ID]
        selected_identifiers = {
            (DOMAIN, f"{event_id}_{participant_id}")
            for participant_id in participant_ids
        }
        registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(registry, self.config_entry.entry_id):
            participant_identifiers = {
                identifier
                for identifier in device.identifiers
                if identifier[0] == DOMAIN and identifier[1].startswith(f"{event_id}_")
            }
            if participant_identifiers and not participant_identifiers & selected_identifiers:
                registry.async_remove_device(device.id)
