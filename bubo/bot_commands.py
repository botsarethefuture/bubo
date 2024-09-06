import csv
import logging
import re
import time

from email_validator import validate_email, EmailNotValidError

# noinspection PyPackageRequirements
from nio import (
    RoomPutStateError,
    RoomGetStateEventError,
    RoomPutStateResponse,
    ProtocolError,
)

# noinspection PyPackageRequirements
from nio.schemas import check_user_id

from bubo import help_strings
from bubo.chat_functions import send_text_to_room, invite_to_room
from bubo.communities import ensure_community_exists
from bubo.rooms import (
    ensure_room_exists,
    create_breakout_room,
    set_user_power,
    get_room_power_levels,
    recreate_room,
)
from bubo.users import (
    list_users,
    get_user_by_attr,
    create_user,
    send_password_reset,
    invite_user,
    create_signup_link,
)
from bubo.utils import get_users_for_access, with_ratelimit, ensure_room_id

logger = logging.getLogger(__name__)

TEXT_PERMISSION_DENIED = "I'm afraid I cannot let you do that."

HELP_POWER = """Set power level in a room. Usage:

`power <user> <room> [<level>]`

* `user` is the user ID, example `@user:example.tld`
* `room` is a room alias or ID, example `#room:example.tld`. Bot must have power to give power there.
* `level` is optional and defaults to `moderator`.

Moderator rights can be given by coordinator level users. To give admin in a room, user must be admin of the bot.
"""


class Command(object):
    def __init__(self, client, store, config, command, room, event):
        """A command made by a user

        Args:
            client (nio.AsyncClient): The client to communicate to matrix with

            store (Storage): Bot storage

            config (Config): Bot configuration parameters

            command (str): The command and arguments

            room (nio.rooms.MatrixRoom): The room the command was sent in

            event (nio.events.room_events.RoomMessageText): The event describing the command
        """
        self.client = client
        self.store = store
        self.config = config
        self.command = command
        self.room = room
        self.event = event
        self.args = self.command.split()[1:]

    async def _ensure_admin(self) -> bool:
        admin_users = await get_users_for_access(self.client, self.config, "admins")
        if self.event.sender not in admin_users:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"{TEXT_PERMISSION_DENIED} Admin level access needed.",
            )
            return False
        return True

    async def _ensure_coordinator(self) -> bool:
        allowed_users = await get_users_for_access(
            self.client, self.config, "coordinators"
        )
        if self.event.sender not in allowed_users:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"{TEXT_PERMISSION_DENIED} Coordinator level access needed.",
            )
            return False
        return True

    async def process(self):
        """Process the command"""
        if self.command.startswith("breakout"):
            await self._breakout()
        elif self.command.startswith("communities"):
            await self._communities()
        elif self.command.startswith("help"):
            await self._show_help()
        elif self.command.startswith("invite"):
            await self._invite()
        elif self.command.startswith("power"):
            await self._power()
        elif self.command.startswith("rooms"):
            await self._rooms()
        elif self.command.startswith("spaces"):
            await self._rooms(space=True)
        elif self.command.startswith("users"):
            await self._users()
        else:
            await self._unknown_command()

    async def _breakout(self):
        """Create a breakout room"""
        help_text = (
            "Creates a breakout room. Usage:\n"
            "\n"
            "breakout TOPIC\n"
            "\n"
            "For example:\n"
            "\n"
            "breakout Bot's are cool\n"
            "\n"
            "Any remaining text after the `breakout` command will be used as the name of the room. "
            "The user requesting the breakout room will be automatically invited to the new room "
            "and made admin. "
            "Other users can react to the bot response message with any emoji reaction to "
            "get invited to the room."
        )
        if not self.args or self.args[0] == "help":
            await send_text_to_room(self.client, self.room.room_id, help_text)
        elif self.args:
            name = " ".join(self.args)
            logger.debug(f"Breakout room name: '{name}'")
            room_id = await create_breakout_room(
                name=name,
                client=self.client,
                created_by=self.event.sender,
            )
            text = f"Breakout room '{name}' created!\n"
            text += "\n\nReact to this message with any emoji reaction to get invited to the room."
            event_id = await send_text_to_room(self.client, self.room.room_id, text)
            if event_id:
                self.store.store_breakout_room(event_id, room_id)
            else:
                text = (
                    "*Error: failed to store breakout room data. The room was created, "
                    "but invites via reactions will not work.*"
                )
                await send_text_to_room(self.client, self.room.room_id, text)

    async def _communities(self):
        """List and operate on communities"""
        if not await self._ensure_coordinator():
            return
        if self.args:
            if self.args[0] == "create":
                # Create a community
                # Figure out the actual parameters
                args = self.args[1:]
                params = csv.reader([" ".join(args)], delimiter=" ")
                params = [param for param in params][0]
                if len(params) != 3 or params[0] == "help":
                    text = (
                        "NOTE! Communities support is deprecated and will be removed in Bubo v0.4.0.\n"
                        "\n"
                        "Wrong number of arguments. Usage:\n"
                        "\n"
                        "`communities create NAME ALIAS TITLE`\n"
                        "\n"
                        "For example:\n"
                        "\n"
                        'communities create "My epic community" epic-community "The best community ever!"\n'
                        "\n"
                        "Note, ALIAS should only contain lower case ascii characters and dashes (maybe)."
                    )
                else:
                    result, error = await ensure_community_exists(
                        (None, params[0], params[1], params[2], None, None),
                        self.config,
                    )
                    if result == "created":
                        text = (
                            f"NOTE! Communities support is deprecated and will be removed in Bubo v0.4.0.\n"
                            f"\n"
                            f"Community {params[0]} (+{params[1]}:{self.config.server_name}) "
                            f"created successfully."
                        )
                        self.store.store_community(params[0], params[1], params[2])
                    elif result == "exists":
                        text = (
                            f"NOTE! Communities support is deprecated and will be removed in Bubo v0.4.0.\n"
                            f"\n"
                            f"Sorry! Community {params[0]} (+{params[1]}:{self.config.server_name}) "
                            f"already exists."
                        )
                    else:
                        text = f"Error creating community: {error}"
            else:
                text = "Unknown subcommand!"
        else:
            text = (
                "NOTE! Communities support is deprecated and will be removed in Bubo v0.4.0.\n"
                "\n"
                "I currently maintain the following communities:\n\n"
            )
            results = self.store.cursor.execute(
                """
                select * from communities
            """
            )
            communities = []
            dbresult = results.fetchall()
            for community in dbresult:
                communities.append(
                    f"* {community[1]} / +{community[2]}:{self.config.server_name} / {community[3]}\n"
                )
            text += "".join(communities)
        await send_text_to_room(self.client, self.room.room_id, text)

    async def _invite(self):
        """Handle an invite command"""
        if not await self._ensure_coordinator():
            return
        if not self.args or self.args[0] == "help":
            await send_text_to_room(
                self.client, self.room.room_id, help_strings.HELP_INVITE
            )
            return

        try:
            room_id = await ensure_room_id(self.client, self.args[0])
        except (AttributeError, ProtocolError):
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"Could not resolve room ID. Please ensure room exists.",
            )
        except IndexError:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"Cannot understand arguments.\n\n{help_strings.HELP_INVITE}",
            )
        else:
            if len(self.args) == 1:
                await invite_to_room(
                    self.client,
                    room_id,
                    self.event.sender,
                    self.room.room_id,
                    self.args[0],
                )
                return
            else:
                for counter, user_id in enumerate(self.args, 1):
                    if counter == 1:
                        # Skip the room ID
                        continue
                    try:
                        check_user_id(user_id)
                    except ValueError:
                        await send_text_to_room(
                            self.client,
                            self.room.room_id,
                            f"Invalid user mxid: {user_id}",
                        )
                    else:
                        await invite_to_room(
                            self.client,
                            room_id,
                            user_id,
                            self.room.room_id,
                            self.args[0],
                        )
                return

    async def _power(self):
        """Set power in a room.

        Coordinators can set moderator power.
        Admins can set also admin power.

        # TODO this does not persist power in rooms maintained with the bot if
        `permissions.demote_users` is set to True - need to make this
        command also save the power in that case, unfortunately we don't yet have
        a database table to track configured user power in rooms and might not
        be adding such a feature anytime soon.
        """
        if not await self._ensure_coordinator():
            return

        if not self.args or self.args[0] == "help":
            text = HELP_POWER
        else:
            try:
                user_id = self.args[0]
                room_id = self.args[1]
                if room_id.startswith("#"):
                    response = await self.client.room_resolve_alias(f"{room_id}")
                    room_id = response.room_id
            except AttributeError:
                text = f"Could not resolve room ID. Please ensure room exists."
            except IndexError:
                text = f"Cannot understand arguments.\n\n{HELP_POWER}"
            else:
                try:
                    level = self.args[2]
                except IndexError:
                    level = "moderator"
                if level not in ("moderator", "admin"):
                    text = f"Level must be 'moderator' or 'admin'."
                else:
                    if level == "admin" and not await self._ensure_admin():
                        text = f"Only bot admins can set admin level power, sorry."
                    else:
                        power = {
                            "admin": 100,
                            "moderator": 50,
                        }.get(level)
                        response = await set_user_power(
                            room_id, user_id, self.client, power
                        )
                        if isinstance(
                            response, (RoomPutStateError, RoomGetStateEventError)
                        ):
                            text = f"Sorry, command failed.\n\n{response.message}"
                        elif isinstance(response, RoomPutStateResponse):
                            text = f"Power level was successfully set as requested."
                        elif isinstance(response, int):
                            if response == 403:
                                text = f"Failed to set power level - no permissions to do so or not in room."
                            else:
                                text = f"Failed to set power level - error code {response}."
                        else:
                            logger.warning(
                                f"Got unexpected set_user_power response: {response}"
                            )
                            text = f"Unknown power level response, please consult the logs."

        await send_text_to_room(self.client, self.room.room_id, text)

    async def _show_help(self):
        """Show the help text"""
        await send_text_to_room(self.client, self.room.room_id, help_strings.HELP_HELP)

    async def _rooms(self, space: bool = False):
        """List and operate on rooms and spaces"""
        if not await self._ensure_coordinator():
            return
        text = None
        type_text = "Space" if space else "Room"
        if self.args:
            if self.args[0] == "create":
                # Create a room or space
                # Figure out the actual parameters
                args = self.args[1:]
                params = csv.reader([" ".join(args)], delimiter=" ")
                params = [param for param in params][0]
                if (
                    len(params) != 5
                    or params[3] not in ("yes", "no")
                    or params[3] not in ("yes", "no")
                    or params[0] == "help"
                ):
                    text = (
                        f"Wrong number or bad arguments. "
                        f"Usage:\n\n{help_strings.HELP_SPACES if space else help_strings.HELP_ROOMS}"
                    )
                else:
                    result, error = await ensure_room_exists(
                        (
                            None,
                            params[0],
                            params[1],
                            None,
                            params[2],
                            None,
                            True if params[3] == "yes" else False,
                            True if params[4] == "yes" else False,
                            "space" if space else "",
                        ),
                        self.client,
                        self.store,
                        self.config,
                    )
                    if result == "created":
                        text = (
                            f"{type_text} {params[0]} (#{params[1]}:{self.config.server_name}) "
                            f"created successfully."
                        )
                    elif result == "exists":
                        text = (
                            f"Sorry! {type_text} {params[0]} (#{params[1]}:{self.config.server_name}) "
                            f"already exists."
                        )
                    else:
                        text = f"Error creating {type_text}: {error}"
            elif self.args[0] == "help":
                text = help_strings.HELP_SPACES if space else help_strings.HELP_ROOMS
            elif self.args[0] == "list":
                text = await self._list_rooms(spaces=space)
            elif self.args[0] == "list-no-admin":
                text = await self._list_no_admin_rooms(spaces=space)
            elif self.args[0] == "recreate":
                return await self._recreate_room(
                    subcommand=self.args[1] if len(self.args) > 1 else None
                )
            elif self.args[0] == "unlink":
                await self._unlink_room(leave=False)
            elif self.args[0] == "unlink-and-leave":
                await self._unlink_room(leave=True)
            else:
                text = "Unknown subcommand!"
        else:
            text = await self._list_rooms()
        if text:
            await send_text_to_room(self.client, self.room.room_id, text)

    async def _list_no_admin_rooms(self, spaces: bool = False):
        text = f"I lack admin power in the following {'spaces' if spaces else 'rooms'} I maintain:\n\n"
        rooms = self.store.get_rooms(spaces=spaces)
        rooms_list = []
        for room in rooms:
            _state, users = await get_room_power_levels(self.client, room["room_id"])
            if users and users.get(self.config.user_id, 0) < 100:
                joined_members = await with_ratelimit(
                    self.client,
                    "joined_members",
                    room_id=room["room_id"],
                )
                user_count = getattr(joined_members, "members", None)
                suffix = ""
                admin_users = [user for user, power in users.items() if power == 100]
                if len(admin_users):
                    suffix = f". **The {'space' if spaces else 'room'} has {len(admin_users)} other admins.**"
                rooms_list.append(
                    f"* {room['name']} / #{room['alias']}:{self.config.server_name} / "
                    f"{room['room_id']} / users: {len(user_count) if user_count else 'unknown'}"
                    f"{suffix}\n"
                )
        text += "".join(rooms_list)
        return text

    async def _list_rooms(self, spaces: bool = False):
        text = (
            f"I currently maintain the following {'spaces' if spaces else 'rooms'}:\n\n"
        )
        rooms = self.store.get_rooms(spaces=spaces)
        rooms_list = []
        for room in rooms:
            rooms_list.append(
                f"* {room['name']} / #{room['alias']}:{self.config.server_name} / {room['room_id']}\n"
            )
        text += "".join(rooms_list)
        return text

    async def _recreate_room(self, subcommand):
        """
        Command to recreate a room. Useful if the room has no admins.
        """
        if not await self._ensure_admin():
            return

        if not subcommand:
            room = self.store.get_recreate_room(self.room.room_id)
            if room:
                if room["applied"] == 1:
                    return await send_text_to_room(
                        self.client,
                        self.room.room_id,
                        "Can only recreate a room once, this room has already been recreated.",
                    )
                self.store.delete_recreate_room(self.room.room_id)
            self.store.store_recreate_room(self.event.sender, self.room.room_id)
            return await send_text_to_room(
                self.client,
                self.room.room_id,
                help_strings.HELP_ROOMS_RECREATE_CONFIRM % self.config.command_prefix,
            )

        if subcommand != "confirm":
            return await send_text_to_room(
                self.client,
                self.room.room_id,
                f"Unknown subcommand. Usage:\n\n{help_strings.HELP_ROOMS_RECREATE}",
            )

        room = self.store.get_recreate_room(self.room.room_id)
        if not room:
            return await send_text_to_room(
                self.client,
                self.room.room_id,
                "Cannot confirm room recreate before requesting room recreate.",
            )
        if room["requester"] != self.event.sender:
            return await send_text_to_room(
                self.client,
                self.room.room_id,
                "Room recreate confirm must be given by the room recreate requester.",
            )
        if int(time.time()) - room["timestamp"] > 60:
            return await send_text_to_room(
                self.client,
                self.room.room_id,
                "Room recreate confirmation must be given within 60 seconds. Please request recreation again.",
            )

        # OK confirmation over, let's do stuff
        new_room_id = await recreate_room(
            self.room, self.client, self.config, self.store, self.event.event_id
        )
        if not new_room_id:
            return await send_text_to_room(
                self.client,
                self.room.room_id,
                f"Failed to create new room. Please see logs or contact support.",
            )

    async def _unknown_command(self):
        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Unknown command '{self.command}'. Try the 'help' command for more information.",
        )

    async def _unlink_room(self, leave: bool):
        """
        Unlink the room by removing from Bubo room database.

        Optionally leave the room as well.
        """
        if not await self._ensure_coordinator():
            return

        if len(self.args) < 2:
            return await send_text_to_room(
                self.client,
                self.room.room_id,
                help_strings.HELP_ROOMS_UNLINK,
            )
        try:
            room_id = await ensure_room_id(self.client, self.args[1])
        except (KeyError, ProtocolError):
            return await send_text_to_room(
                self.client,
                self.room.room_id,
                f"Error resolving room ID",
            )

        room = self.store.get_room(room_id)
        if not room:
            return await send_text_to_room(
                self.client,
                self.room.room_id,
                f"Cannot unlink room {room_id} which doesn't seem tracked by Bubo",
            )

        self.store.unlink_room(room_id)

        if leave:
            await self.client.room_leave(room_id)

        return await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Room {room_id} has been removed from Bubo database."
            f"{' Bubo has also left the room' if leave else ''}",
        )

    async def _users(self):
        """
        Command to manage users.
        """
        if not self.config.keycloak.get("enabled"):
            return await send_text_to_room(
                self.client,
                self.room.room_id,
                help_strings.HELP_USERS_KEYCLOAK_DISABLED,
            )
        text = None
        if self.args:
            if self.args[0] == "list":
                if not await self._ensure_admin():
                    return
                users = list_users(self.config)
                text = f"The following usernames were found: {', '.join([user['username'] for user in users])}"
            elif self.args[0] == "help":
                text = help_strings.HELP_USERS
            elif self.args[0] == "create":
                if not await self._ensure_admin():
                    return
                if len(self.args) == 1 or self.args[1] == "help":
                    text = help_strings.HELP_USERS_CREATE
                else:
                    emails = self.args[1:]
                    emails = {email.strip() for email in emails}
                    texts = []
                    for email in emails:
                        try:
                            validated = validate_email(email)
                            email = validated.email
                            logger.debug("users create - Email %s is valid", email)
                        except EmailNotValidError as ex:
                            texts.append(f"The email {email} looks invalid: {ex}")
                            continue
                        try:
                            existing_user = get_user_by_attr(
                                self.config, "email", email
                            )
                        except Exception as ex:
                            texts.append(
                                f"Error looking up existing users by email {email}: {ex}"
                            )
                            continue
                        if existing_user:
                            texts.append(
                                f"Found an existing user by email {email} - ignoring"
                            )
                            continue
                        logger.debug(
                            "users create - No existing user for %s found", email
                        )
                        username = None
                        username_candidate = email.split("@")[0]
                        username_candidate = username_candidate.lower()
                        username_candidate = re.sub(
                            r"[^a-z0-9._\-]", "", username_candidate
                        )
                        candidate = username_candidate
                        counter = 0
                        while not username:
                            logger.debug("users create - candidate: %s", candidate)
                            # noinspection PyBroadException
                            try:
                                existing_user = get_user_by_attr(
                                    self.config, "username", candidate
                                )
                            except Exception:
                                existing_user = True
                            if existing_user:
                                logger.debug(
                                    "users create - Found existing user with candidate %s",
                                    existing_user,
                                )
                                counter += 1
                                candidate = f"{username_candidate}{counter}"
                                continue
                            username = candidate
                            logger.debug("Username is %s", username)
                        user_id = create_user(self.config, username, email)
                        logger.debug("Created user: %s", user_id)
                        if not user_id:
                            texts.append(f"Failed to create user for email {email}")
                            logger.warning(
                                "users create - Failed to create user for email %s",
                                email,
                            )
                            continue
                        send_password_reset(self.config, user_id)
                        logger.info(
                            "users create - Successfully create user with email %s",
                            email,
                        )
                        texts.append(f"Successfully create {email}!")
                    text = "\n".join(texts)
            elif self.args[0] == "invite":
                if not await self._ensure_coordinator():
                    return
                if not self.config.keycloak_signup.get("enabled"):
                    return await send_text_to_room(
                        self.client,
                        self.room.room_id,
                        help_strings.HELP_USERS_KEYCLOAK_SIGNUP_DISABLED,
                    )
                if len(self.args) == 1 or self.args[1] == "help":
                    return await send_text_to_room(
                        self.client, self.room.room_id, help_strings.HELP_USERS_INVITE
                    )
                emails = self.args[1:]
                emails = {email.strip() for email in emails}
                texts = []
                for email in emails:
                    try:
                        validated = validate_email(email)
                        email = validated.email
                        logger.debug("users invite - Email %s is valid", email)
                    except EmailNotValidError as ex:
                        texts.append(f"The email {email} looks invalid: {ex}")
                        continue

                    try:
                        invite_user(self.config, email, self.event.sender)
                    except Exception as ex:
                        logger.error(
                            "users invite - error sending invite to user: %s", ex
                        )
                        texts.append(f"Error inviting {email}, please see logs.")
                        continue
                    logger.debug("users invite - Invited user: %s", email)
                    texts.append(f"Successfully invited {email}!")
                text = "\n".join(texts)
            elif self.args[0] == "signuplink":
                if not await self._ensure_coordinator():
                    return
                if not self.config.keycloak_signup.get("enabled"):
                    return await send_text_to_room(
                        self.client,
                        self.room.room_id,
                        help_strings.HELP_USERS_KEYCLOAK_SIGNUP_DISABLED,
                    )
                if len(self.args) < 3 or self.args[1] == "help":
                    return await send_text_to_room(
                        self.client,
                        self.room.room_id,
                        help_strings.HELP_USERS_SIGNUPLINK,
                    )
                try:
                    max_signups = int(self.args[1])
                    days_valid = int(self.args[2])
                    if max_signups < 1 or days_valid < 1:
                        raise ValueError
                except ValueError:
                    return await send_text_to_room(
                        self.client,
                        self.room.room_id,
                        help_strings.HELP_USERS_SIGNUPLINK,
                    )
                # noinspection PyBroadException
                try:
                    signup_link = create_signup_link(
                        self.config, self.event.sender, max_signups, days_valid
                    )
                except Exception as ex:
                    logger.error("Failed to create signup link: %s", ex)
                    text = (
                        "Error creating signup link. Please contact an administrator."
                    )
                else:
                    logger.info(
                        f"Successfully created signup link requested by {self.event.sender}"
                    )
                    text = (
                        f"Signup link created for {max_signups} signups with a validity of {days_valid} days. "
                        f"The link is {signup_link}"
                    )
        else:
            if not await self._ensure_admin():
                return
            users = list_users(self.config)
            text = f"The following usernames were found: {', '.join([user['username'] for user in users])}"
        if not text:
            text = help_strings.HELP_USERS
        await send_text_to_room(self.client, self.room.room_id, text)
