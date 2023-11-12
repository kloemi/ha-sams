"""Config flow for samsvolleyball integration."""
from __future__ import annotations

import logging
import json
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

import urllib.parse

from . import SamsDataCoordinator
from .utils import get_leaguelist, get_teamlist, get_league_data

from .const import (
    DOMAIN,
    DEFAULT_OPTIONS,
    CONF_HOST,
    CONF_LEAGUE,
    CONF_LEAGUE_GENDER,
    CONF_LEAGUE_NAME,
    CONF_REGION,
    CONF_REGION_LIST,
    CONF_TEAM_NAME,
    CONF_TEAM_UUID,
    CONFIG_ENTRY_VERSION,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_OPTIONS[CONF_NAME]): str,
        vol.Required(CONF_HOST, default=DEFAULT_OPTIONS[CONF_HOST]): str,
        vol.Required(CONF_REGION, default=DEFAULT_OPTIONS[CONF_REGION]): vol.In(CONF_REGION_LIST),
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    url = urllib.parse.urljoin(data[CONF_HOST], data[CONF_REGION])
    session = async_get_clientsession(hass)
    coordinator = SamsDataCoordinator(hass, session, "ConfigValidate", url)

    try:
        data = await coordinator.data_received()
    except Exception as exc:
        raise CannotConnect from exc
    if not data:
        raise InvalidData

    leagues = get_leaguelist(data)
    if 0 == len(leagues):
       raise InvalidData

    # Return info that you want to store in the config entry.
    return data, leagues

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for samsvolleyball."""

    VERSION = CONFIG_ENTRY_VERSION

    cfg_data: Optional[Dict[str, Any]]
    data = None
    leagues: dict[str, str] = None
    teams: dict[str, str] = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self.data, self.leagues = await validate_input(self.hass, user_input)
                self.cfg_data = user_input
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidData:
                errors["base"] = "invalid_data"
            except TeamNotFound:
                errors["base"] = "invalid_team"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return await self.async_step_league()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_league(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            league_id = self.leagues[user_input[CONF_LEAGUE]]
            self.teams = get_teamlist(self.data, league_id)
            self.cfg_data[CONF_LEAGUE_GENDER] =  get_league_data(self.data, league_id, CONF_LEAGUE_GENDER)
            self.cfg_data[CONF_LEAGUE_NAME] =  get_league_data(self.data, league_id, "name")
            if 0 == len(self.teams):
                errors["base"] = "no_teams"
            else:
                self.cfg_data[CONF_LEAGUE] = user_input[CONF_LEAGUE]
                return await self.async_step_team()

        step_league_schema = vol.Schema(
            {
                vol.Required(CONF_LEAGUE): vol.In(list(self.leagues.keys())),
            }
        )
        return self.async_show_form(
            step_id="league", data_schema=step_league_schema, errors=errors
        )

    async def async_step_team(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:

        if user_input is not None:
            self.cfg_data[CONF_TEAM_NAME] = user_input[CONF_TEAM_NAME]
            team_id = self.teams[user_input[CONF_TEAM_NAME]]
            self.cfg_data[CONF_TEAM_UUID] = team_id

            devicename = f"{user_input[CONF_TEAM_NAME]} ({self.cfg_data[CONF_LEAGUE_NAME]})"
            return self.async_create_entry(title=devicename, data=self.cfg_data)

        step_team_schema = vol.Schema(
            {
                vol.Required(CONF_TEAM_NAME): vol.In(list(self.teams.keys())),
            }
        )
        return self.async_show_form(
            step_id="team", data_schema=step_team_schema
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidData(HomeAssistantError):
    """Error to indicate we received invalid data."""

class TeamNotFound(HomeAssistantError):
    """Error to indicate the school is not found."""